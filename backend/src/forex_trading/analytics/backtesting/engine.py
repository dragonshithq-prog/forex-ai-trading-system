"""Event-driven backtesting engine with full trade simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID, uuid4

import numpy as np
import structlog

logger = structlog.get_logger()

# Pip size per instrument family
_PIP_SIZE: dict[str, float] = {}  # populated lazily


def _pip_size(symbol: str) -> float:
    """Return pip size for a symbol. JPY pairs = 0.01, others = 0.0001."""
    if "JPY" in symbol.upper():
        return 0.01
    return 0.0001


@dataclass
class BacktestConfig:
    strategy_type: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float = 10_000.0
    risk_per_trade_pct: float = 1.0
    commission_per_lot: float = 7.0  # USD per round trip per lot
    slippage_pips: float = 0.5
    spread_pips: float = 1.5
    leverage: int = 100
    parameters: dict = field(default_factory=dict)


@dataclass
class BacktestTrade:
    trade_id: UUID
    symbol: str
    direction: str  # "long" | "short"
    entry_price: float
    exit_price: float
    size: float  # lots
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pips: float
    commission: float
    slippage: float
    stop_loss: float
    take_profit: float
    exit_reason: str  # "tp_hit" | "sl_hit" | "trailing_stop" | "time_exit" | "signal_exit"
    max_favorable_excursion: float  # MFE
    max_adverse_excursion: float  # MAE
    r_multiple: float  # pnl / initial_risk


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[BacktestTrade]

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    profit_factor: float
    gross_profit: float
    gross_loss: float
    net_profit: float

    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    max_drawdown_pct: float
    max_drawdown_duration_days: int

    avg_win_pips: float
    avg_loss_pips: float
    avg_r_multiple: float
    expectancy: float  # avg R per trade

    initial_balance: float
    final_balance: float
    total_return_pct: float

    monthly_returns: dict[str, float]  # "2024-01": 2.5
    equity_curve: list[tuple[datetime, float]]

    start_date: datetime
    end_date: datetime
    duration_days: int

    run_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


class BacktestEngine:
    """
    Event-driven backtesting engine.

    Simulates trading by replaying historical OHLCV data candle by candle.
    Supports long and short positions with SL/TP evaluation against each
    candle's High/Low, commission, slippage, and MFE/MAE tracking.
    """

    def __init__(self, data_provider: Callable) -> None:
        """
        Args:
            data_provider: Async callable(symbol, start, end, timeframe) -> list[dict]
                Each dict must contain: timestamp, open, high, low, close, volume
        """
        self._data_provider = data_provider

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Run a complete backtest. Returns full performance metrics."""
        logger.info(
            "backtest_started",
            strategy=config.strategy_type,
            symbol=config.symbol,
            start=config.start_date.isoformat(),
            end=config.end_date.isoformat(),
        )

        candles: list[dict] = await self._data_provider(
            config.symbol, config.start_date, config.end_date, config.timeframe
        )
        if not candles:
            logger.warning("backtest_no_candles", symbol=config.symbol)
            return self._empty_result(config)

        candles = sorted(candles, key=lambda c: c["timestamp"])

        strategy_fn = self._get_strategy_fn(config.strategy_type)
        trades: list[BacktestTrade] = []
        equity = config.initial_balance
        equity_curve: list[tuple[datetime, float]] = [(candles[0]["timestamp"], equity)]

        # State: at most one open trade at a time (single-position mode)
        i = 0
        while i < len(candles):
            candle = candles[i]

            # Check for entry signal on this candle
            if i >= 20:  # need warmup candles for indicators
                signal = strategy_fn(candles[: i + 1], config)
                if signal is not None:
                    direction, sl_price, tp_price = signal
                    entry_price = self._apply_slippage(
                        candle["close"], direction, config.slippage_pips, config.symbol
                    )
                    # Spread adjustment for entries
                    if direction == "long":
                        entry_price += config.spread_pips * _pip_size(config.symbol)

                    size = self._calculate_position_size(
                        entry_price, sl_price, config, equity
                    )

                    if size > 0 and i + 1 < len(candles):
                        trade = self._simulate_trade(
                            entry_candle=candle,
                            candles=candles[i + 1:],
                            entry_price=entry_price,
                            direction=direction,
                            stop_loss=sl_price,
                            take_profit=tp_price,
                            size=size,
                            config=config,
                        )
                        trades.append(trade)
                        equity += trade.pnl
                        equity_curve.append((trade.exit_time, equity))

                        # Advance index past the trade exit
                        exit_ts = trade.exit_time
                        while i < len(candles) and candles[i]["timestamp"] <= exit_ts:
                            i += 1
                        continue

            equity_curve.append((candle["timestamp"], equity))
            i += 1

        result = self._calculate_metrics(trades, config)
        logger.info(
            "backtest_completed",
            run_id=str(result.run_id),
            trades=result.total_trades,
            net_profit=result.net_profit,
            sharpe=result.sharpe_ratio,
        )
        return result

    def _simulate_trade(
        self,
        entry_candle: dict,
        candles: list[dict],
        entry_price: float,
        direction: str,
        stop_loss: float,
        take_profit: float,
        size: float,
        config: BacktestConfig,
    ) -> BacktestTrade:
        """
        Simulate a single trade candle by candle until SL, TP, or data exhaustion.

        For each candle: first check if SL is hit (worst case), then TP (best case).
        This conservative ordering prevents over-optimistic results.
        """
        pip = _pip_size(config.symbol)
        initial_risk_pips = abs(entry_price - stop_loss) / pip
        mfe_pips = 0.0
        mae_pips = 0.0

        for candle in candles:
            high = candle["high"]
            low = candle["low"]
            ts = candle["timestamp"]

            if direction == "long":
                # MFE / MAE tracking
                favorable = (high - entry_price) / pip
                adverse = (entry_price - low) / pip
                mfe_pips = max(mfe_pips, favorable)
                mae_pips = max(mae_pips, adverse)

                # SL check (conservative first)
                if low <= stop_loss:
                    return self._close_trade(
                        entry_candle, ts, entry_price, stop_loss, direction,
                        size, config, "sl_hit", mfe_pips, mae_pips,
                        initial_risk_pips, pip,
                    )
                # TP check
                if high >= take_profit:
                    return self._close_trade(
                        entry_candle, ts, entry_price, take_profit, direction,
                        size, config, "tp_hit", mfe_pips, mae_pips,
                        initial_risk_pips, pip,
                    )
            else:  # short
                favorable = (entry_price - low) / pip
                adverse = (high - entry_price) / pip
                mfe_pips = max(mfe_pips, favorable)
                mae_pips = max(mae_pips, adverse)

                if high >= stop_loss:
                    return self._close_trade(
                        entry_candle, ts, entry_price, stop_loss, direction,
                        size, config, "sl_hit", mfe_pips, mae_pips,
                        initial_risk_pips, pip,
                    )
                if low <= take_profit:
                    return self._close_trade(
                        entry_candle, ts, entry_price, take_profit, direction,
                        size, config, "tp_hit", mfe_pips, mae_pips,
                        initial_risk_pips, pip,
                    )

        # Time exit: close at last candle close
        last = candles[-1] if candles else entry_candle
        exit_price = last["close"]
        return self._close_trade(
            entry_candle, last["timestamp"], entry_price, exit_price, direction,
            size, config, "time_exit", mfe_pips, mae_pips, initial_risk_pips, pip,
        )

    def _close_trade(
        self,
        entry_candle: dict,
        exit_time: datetime,
        entry_price: float,
        exit_price: float,
        direction: str,
        size: float,
        config: BacktestConfig,
        exit_reason: str,
        mfe_pips: float,
        mae_pips: float,
        initial_risk_pips: float,
        pip: float,
    ) -> BacktestTrade:
        commission = config.commission_per_lot * size
        slippage_cost = config.slippage_pips * pip * size * 100_000

        if direction == "long":
            raw_pnl_pips = (exit_price - entry_price) / pip
        else:
            raw_pnl_pips = (entry_price - exit_price) / pip

        # 1 standard lot = 100,000 units; pip value ~$10/pip for XXXUSD at 1 lot
        # PnL = pips * pip_value_per_lot * size
        pip_value_per_lot = 10.0  # approximate; refined per-symbol in production
        raw_pnl = raw_pnl_pips * pip_value_per_lot * size
        net_pnl = raw_pnl - commission - slippage_cost

        r_multiple = net_pnl / (initial_risk_pips * pip_value_per_lot * size) if initial_risk_pips > 0 else 0.0

        return BacktestTrade(
            trade_id=uuid4(),
            symbol=config.symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            entry_time=entry_candle["timestamp"],
            exit_time=exit_time,
            pnl=net_pnl,
            pnl_pips=raw_pnl_pips,
            commission=commission,
            slippage=slippage_cost,
            stop_loss=entry_price - initial_risk_pips * pip if direction == "long" else entry_price + initial_risk_pips * pip,
            take_profit=exit_price,
            exit_reason=exit_reason,
            max_favorable_excursion=mfe_pips,
            max_adverse_excursion=mae_pips,
            r_multiple=r_multiple,
        )

    def _calculate_metrics(
        self, trades: list[BacktestTrade], config: BacktestConfig
    ) -> BacktestResult:
        if not trades:
            return self._empty_result(config)

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        net_profit = gross_profit - gross_loss

        profit_factor = self._calculate_profit_factor(trades)

        # Build equity curve
        equity = config.initial_balance
        raw_equity: list[float] = [equity]
        equity_curve: list[tuple[datetime, float]] = [(config.start_date, equity)]
        daily_pnls: dict[str, float] = {}

        for t in sorted(trades, key=lambda x: x.exit_time):
            equity += t.pnl
            equity_curve.append((t.exit_time, equity))
            raw_equity.append(equity)
            day_key = t.exit_time.strftime("%Y-%m-%d")
            daily_pnls[day_key] = daily_pnls.get(day_key, 0.0) + t.pnl

        final_balance = equity
        total_return_pct = (final_balance - config.initial_balance) / config.initial_balance * 100.0

        daily_returns = [v / config.initial_balance for v in daily_pnls.values()]
        sharpe = self._calculate_sharpe(daily_returns)
        sortino = self._calculate_sortino(daily_returns)
        max_dd_pct, max_dd_days = self._calculate_max_drawdown(raw_equity)
        annualized_return = (1 + total_return_pct / 100) ** (252 / max(len(daily_returns), 1)) - 1
        calmar = annualized_return / (max_dd_pct / 100.0) if max_dd_pct > 0 else 0.0

        avg_win_pips = sum(t.pnl_pips for t in wins) / len(wins) if wins else 0.0
        avg_loss_pips = sum(t.pnl_pips for t in losses) / len(losses) if losses else 0.0

        r_multiples = [t.r_multiple for t in trades]
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

        win_rate = len(wins) / len(trades)
        avg_win = gross_profit / len(wins) if wins else 0.0
        avg_loss_abs = gross_loss / len(losses) if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss_abs)

        monthly_returns = self._compute_monthly_returns(trades, config.initial_balance)

        duration_days = (config.end_date - config.start_date).days

        return BacktestResult(
            config=config,
            trades=trades,
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            profit_factor=profit_factor,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration_days=max_dd_days,
            avg_win_pips=avg_win_pips,
            avg_loss_pips=avg_loss_pips,
            avg_r_multiple=avg_r,
            expectancy=expectancy,
            initial_balance=config.initial_balance,
            final_balance=final_balance,
            total_return_pct=total_return_pct,
            monthly_returns=monthly_returns,
            equity_curve=equity_curve,
            start_date=config.start_date,
            end_date=config.end_date,
            duration_days=duration_days,
        )

    def _calculate_sharpe(self, returns: list[float], risk_free_daily: float = 0.02 / 252) -> float:
        """Annualized Sharpe = (mean_daily - Rf_daily) / std_daily * sqrt(252)."""
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=float)
        excess = arr - risk_free_daily
        std = float(np.std(excess, ddof=1))
        if std == 0.0:
            return 0.0
        return float(np.mean(excess) / std * math.sqrt(252))

    def _calculate_sortino(self, returns: list[float], risk_free_daily: float = 0.02 / 252) -> float:
        """Annualized Sortino = (mean_daily - Rf_daily) / downside_std * sqrt(252)."""
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=float)
        mean_excess = float(np.mean(arr)) - risk_free_daily
        downside = arr[arr < 0]
        if len(downside) == 0:
            return float("inf") if mean_excess > 0 else 0.0
        downside_std = float(np.std(downside, ddof=1))
        if downside_std == 0.0:
            return 0.0
        return float(mean_excess / downside_std * math.sqrt(252))

    def _calculate_max_drawdown(self, equity_curve: list[float]) -> tuple[float, int]:
        """Returns (max_drawdown_pct, max_drawdown_duration_days)."""
        if not equity_curve:
            return 0.0, 0
        arr = np.array(equity_curve, dtype=float)
        peak = np.maximum.accumulate(arr)
        drawdown = (peak - arr) / np.where(peak > 0, peak, 1.0)
        max_dd = float(np.max(drawdown)) * 100.0

        # Duration: longest streak where equity is below its running peak
        in_dd = drawdown > 0
        max_streak = 0
        streak = 0
        for v in in_dd:
            streak = streak + 1 if v else 0
            max_streak = max(max_streak, streak)

        return max_dd, max_streak

    def _calculate_profit_factor(self, trades: list[BacktestTrade]) -> float:
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl <= 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def _apply_slippage(self, price: float, direction: str, slippage_pips: float, symbol: str) -> float:
        pip = _pip_size(symbol)
        slip = slippage_pips * pip
        return price + slip if direction == "long" else price - slip

    def _calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        config: BacktestConfig,
        current_equity: float,
    ) -> float:
        """Risk-based position sizing: risk_pct of equity / (SL distance in $)."""
        pip = _pip_size(config.symbol)
        sl_pips = abs(entry_price - stop_loss) / pip
        if sl_pips == 0:
            return 0.0
        risk_amount = current_equity * (config.risk_per_trade_pct / 100.0)
        pip_value_per_lot = 10.0
        size = risk_amount / (sl_pips * pip_value_per_lot)
        return round(max(0.01, min(size, 100.0)), 2)

    def _compute_monthly_returns(
        self, trades: list[BacktestTrade], initial_balance: float
    ) -> dict[str, float]:
        monthly: dict[str, float] = {}
        for t in trades:
            key = t.exit_time.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0.0) + t.pnl
        return {k: v / initial_balance * 100.0 for k, v in sorted(monthly.items())}

    def _get_strategy_fn(
        self, strategy_type: str
    ) -> Callable[[list[dict], BacktestConfig], tuple[str, float, float] | None]:
        """Return a strategy signal function matching the strategy_type."""
        strategies = {
            "trend_following": _trend_following_signal,
            "mean_reversion": _mean_reversion_signal,
            "breakout": _breakout_signal,
        }
        fn = strategies.get(strategy_type)
        if fn is None:
            logger.warning("unknown_strategy_type", strategy_type=strategy_type, fallback="trend_following")
            fn = _trend_following_signal
        return fn

    def _empty_result(self, config: BacktestConfig) -> BacktestResult:
        return BacktestResult(
            config=config,
            trades=[],
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            net_profit=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration_days=0,
            avg_win_pips=0.0,
            avg_loss_pips=0.0,
            avg_r_multiple=0.0,
            expectancy=0.0,
            initial_balance=config.initial_balance,
            final_balance=config.initial_balance,
            total_return_pct=0.0,
            monthly_returns={},
            equity_curve=[(config.start_date, config.initial_balance)],
            start_date=config.start_date,
            end_date=config.end_date,
            duration_days=(config.end_date - config.start_date).days,
        )


# ---------------------------------------------------------------------------
# Built-in strategy signal functions
# ---------------------------------------------------------------------------

def _trend_following_signal(
    candles: list[dict], config: BacktestConfig
) -> tuple[str, float, float] | None:
    """EMA 20/50 crossover with ATR-based SL/TP."""
    if len(candles) < 51:
        return None
    closes = np.array([c["close"] for c in candles], dtype=float)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    atr = _atr(candles, 14)

    sl_mult = config.parameters.get("stop_loss_atr_multiplier", 1.5)
    tp_mult = config.parameters.get("take_profit_atr_multiplier", 3.0)

    # Detect crossover on last two candles
    if ema20[-2] <= ema50[-2] and ema20[-1] > ema50[-1]:
        price = closes[-1]
        return "long", price - sl_mult * atr, price + tp_mult * atr
    if ema20[-2] >= ema50[-2] and ema20[-1] < ema50[-1]:
        price = closes[-1]
        return "short", price + sl_mult * atr, price - tp_mult * atr
    return None


def _mean_reversion_signal(
    candles: list[dict], config: BacktestConfig
) -> tuple[str, float, float] | None:
    """Bollinger Band mean reversion."""
    if len(candles) < 21:
        return None
    closes = np.array([c["close"] for c in candles[-20:]], dtype=float)
    mid = float(np.mean(closes))
    std = float(np.std(closes, ddof=1))
    price = closes[-1]
    bb_mult = config.parameters.get("bb_multiplier", 2.0)
    upper = mid + bb_mult * std
    lower = mid - bb_mult * std
    atr = _atr(candles, 14)

    if price <= lower:
        return "long", price - 1.5 * atr, mid
    if price >= upper:
        return "short", price + 1.5 * atr, mid
    return None


def _breakout_signal(
    candles: list[dict], config: BacktestConfig
) -> tuple[str, float, float] | None:
    """Donchian channel breakout."""
    period = config.parameters.get("breakout_period", 20)
    if len(candles) < period + 1:
        return None
    recent = candles[-(period + 1):-1]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    current = candles[-1]
    atr = _atr(candles, 14)

    if current["close"] > max(highs):
        return "long", current["close"] - 1.5 * atr, current["close"] + 3.0 * atr
    if current["close"] < min(lows):
        return "short", current["close"] + 1.5 * atr, current["close"] - 3.0 * atr
    return None


# ---------------------------------------------------------------------------
# Technical helpers
# ---------------------------------------------------------------------------

def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    result = np.empty_like(arr)
    k = 2.0 / (period + 1)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = arr[i] * k + result[i - 1] * (1.0 - k)
    return result


def _atr(candles: list[dict], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.001
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    if not trs:
        return 0.001
    recent = trs[-period:]
    return float(np.mean(recent))
