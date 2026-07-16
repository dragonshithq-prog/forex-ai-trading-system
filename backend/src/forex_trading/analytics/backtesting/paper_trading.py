"""Paper trading simulator - live strategy execution with virtual account."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class VirtualPosition:
    position_id: str
    symbol: str
    direction: str  # "long" | "short"
    size: float  # lots
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    unrealized_pnl: float = 0.0
    strategy_type: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class VirtualFill:
    order_id: str
    symbol: str
    direction: str
    size: float
    fill_price: float
    filled_at: datetime
    commission: float
    slippage: float
    status: str = "filled"


class PaperTradingEngine:
    """
    Paper trading simulator - runs live strategy on real market data
    but simulates execution with a virtual account.

    Identical to live trading except:
    - Orders are filled at current market price (simulated)
    - No real broker connection needed
    - Tracks virtual P&L

    Uses dependency injection for market data, risk, and strategy engines
    to maintain identical code paths to live trading.
    """

    _COMMISSION_PER_LOT = 7.0  # USD round-trip
    _SLIPPAGE_PIPS = 0.3
    _PIP_VALUE_PER_LOT = 10.0

    def __init__(
        self,
        market_data_service: Any,
        risk_engine: Any,
        strategy_engine: Any,
        ai_orchestrator: Any,
        initial_balance: float = 10_000.0,
    ) -> None:
        self._market_data = market_data_service
        self._risk_engine = risk_engine
        self._strategy_engine = strategy_engine
        self._ai_orchestrator = ai_orchestrator

        self._initial_balance = initial_balance
        self._virtual_balance = initial_balance
        self._realized_pnl = 0.0

        self._positions: dict[str, VirtualPosition] = {}
        self._closed_trades: list[dict] = []
        self._fill_history: list[VirtualFill] = []

        self._running = False
        self._tick_count = 0
        self._start_time: datetime | None = None

    async def start(self) -> None:
        """Start the paper trading engine."""
        if self._running:
            logger.warning("paper_trading_already_running")
            return
        self._running = True
        self._start_time = datetime.utcnow()
        logger.info(
            "paper_trading_started",
            initial_balance=self._initial_balance,
        )

    async def stop(self) -> None:
        """Stop the paper trading engine and close all positions at market."""
        if not self._running:
            return
        self._running = False

        for pos_id in list(self._positions.keys()):
            pos = self._positions[pos_id]
            await self._close_position(pos_id, pos.current_price, "engine_stop")

        logger.info(
            "paper_trading_stopped",
            total_trades=len(self._closed_trades),
            realized_pnl=self._realized_pnl,
        )

    async def process_tick(self, symbol: str, price: float) -> None:
        """
        Process a market tick. Updates open positions and checks for signal entries.

        Args:
            symbol: Currency pair symbol (e.g. "EURUSD")
            price: Current mid-price
        """
        if not self._running:
            return

        self._tick_count += 1

        # Update unrealized PnL for open positions on this symbol
        for pos in list(self._positions.values()):
            if pos.symbol != symbol:
                continue
            pos.current_price = price
            pos.unrealized_pnl = self._calc_pnl(pos)

            # Check SL/TP
            if pos.direction == "long":
                if price <= pos.stop_loss:
                    await self._close_position(pos.position_id, price, "sl_hit")
                    continue
                if price >= pos.take_profit:
                    await self._close_position(pos.position_id, price, "tp_hit")
                    continue
            else:
                if price >= pos.stop_loss:
                    await self._close_position(pos.position_id, price, "sl_hit")
                    continue
                if price <= pos.take_profit:
                    await self._close_position(pos.position_id, price, "tp_hit")
                    continue

        # Generate signals for entry (every N ticks to reduce compute)
        if self._tick_count % 10 == 0:
            await self._check_for_entry(symbol, price)

    async def simulate_fill(self, order: dict) -> dict:
        """
        Simulate an order fill at the current market price.

        Args:
            order: Dict with keys: symbol, direction, size, stop_loss, take_profit,
                   strategy_type, [entry_price]

        Returns:
            Fill confirmation dict.
        """
        symbol = order["symbol"]
        direction = order["direction"]
        size = float(order.get("size", 0.01))
        stop_loss = float(order["stop_loss"])
        take_profit = float(order["take_profit"])
        strategy_type = order.get("strategy_type", "unknown")

        from forex_trading.analytics.backtesting.engine import _pip_size
        pip = _pip_size(symbol)

        # Simulate slippage
        slippage_amount = self._SLIPPAGE_PIPS * pip
        if direction == "long":
            fill_price = order.get("entry_price", 0.0) + slippage_amount
        else:
            fill_price = order.get("entry_price", 0.0) - slippage_amount

        commission = self._COMMISSION_PER_LOT * size
        self._virtual_balance -= commission

        position_id = str(uuid.uuid4())
        position = VirtualPosition(
            position_id=position_id,
            symbol=symbol,
            direction=direction,
            size=size,
            entry_price=fill_price,
            current_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=datetime.utcnow(),
            strategy_type=strategy_type,
            metadata=order.get("metadata", {}),
        )
        self._positions[position_id] = position

        fill = VirtualFill(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            size=size,
            fill_price=fill_price,
            filled_at=datetime.utcnow(),
            commission=commission,
            slippage=slippage_amount * size * 100_000,
        )
        self._fill_history.append(fill)

        logger.info(
            "paper_trade_filled",
            symbol=symbol,
            direction=direction,
            size=size,
            fill_price=fill_price,
            position_id=position_id,
        )

        return {
            "status": "filled",
            "position_id": position_id,
            "fill_price": fill_price,
            "commission": commission,
            "symbol": symbol,
            "direction": direction,
            "size": size,
        }

    def get_virtual_account(self) -> dict:
        """Return current virtual account state."""
        unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        equity = self._virtual_balance + unrealized_pnl

        return {
            "initial_balance": self._initial_balance,
            "cash_balance": self._virtual_balance,
            "unrealized_pnl": unrealized_pnl,
            "equity": equity,
            "realized_pnl": self._realized_pnl,
            "total_return_pct": (equity - self._initial_balance) / self._initial_balance * 100.0,
            "open_positions": len(self._positions),
            "total_trades": len(self._closed_trades),
            "is_running": self._running,
            "started_at": self._start_time.isoformat() if self._start_time else None,
        }

    def get_virtual_positions(self) -> list[dict]:
        """Return all currently open virtual positions."""
        return [
            {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "direction": p.direction,
                "size": p.size,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "unrealized_pnl": p.unrealized_pnl,
                "opened_at": p.opened_at.isoformat(),
                "strategy_type": p.strategy_type,
            }
            for p in self._positions.values()
        ]

    def get_performance_summary(self) -> dict:
        """Compute a quick performance summary from closed trades."""
        if not self._closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_profit": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "avg_pnl": 0.0,
            }

        pnls = [t["pnl"] for t in self._closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return {
            "total_trades": len(self._closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(pnls),
            "profit_factor": pf,
            "net_profit": sum(pnls),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _close_position(
        self, position_id: str, exit_price: float, reason: str
    ) -> None:
        pos = self._positions.pop(position_id, None)
        if pos is None:
            return

        pnl = self._calc_pnl_at(pos, exit_price)
        self._realized_pnl += pnl
        self._virtual_balance += pnl

        closed_record = {
            "position_id": position_id,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "size": pos.size,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "exit_reason": reason,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": datetime.utcnow().isoformat(),
            "strategy_type": pos.strategy_type,
        }
        self._closed_trades.append(closed_record)

        logger.info(
            "paper_trade_closed",
            symbol=pos.symbol,
            direction=pos.direction,
            pnl=pnl,
            reason=reason,
        )

    def _calc_pnl(self, pos: VirtualPosition) -> float:
        return self._calc_pnl_at(pos, pos.current_price)

    def _calc_pnl_at(self, pos: VirtualPosition, price: float) -> float:
        from forex_trading.analytics.backtesting.engine import _pip_size
        pip = _pip_size(pos.symbol)
        if pos.direction == "long":
            pips = (price - pos.entry_price) / pip
        else:
            pips = (pos.entry_price - price) / pip
        return pips * self._PIP_VALUE_PER_LOT * pos.size

    async def _check_for_entry(self, symbol: str, price: float) -> None:
        """Check AI orchestrator for a new signal and open paper trade if approved."""
        try:
            if any(p.symbol == symbol for p in self._positions.values()):
                return

            candles = await self._market_data.get_ohlcv(symbol, "H1", limit=100)
            if not candles or len(candles) < 20:
                return

            from forex_trading.ai.agents.base import MarketContext, MarketRegime

            context = MarketContext(
                symbol=symbol,
                timeframe="H1",
                candles=candles,
                metadata={"entry_price": price, "symbol": symbol},
                regime=MarketRegime.RANGING,
            )
            result = await self._ai_orchestrator.analyze(context)

            if not result.should_trade:
                return

            direction = result.consensus.direction.value
            assessment = await self._risk_engine.assess_trade(
                symbol=symbol,
                side=direction,
                size=result.consensus.confidence * 0.01,
                entry_price=price,
                stop_loss=None,
            )
            if not assessment.is_approved:
                logger.debug("paper_trade_rejected_by_risk", symbol=symbol)
                return

            await self.simulate_fill({
                "symbol": symbol,
                "direction": direction,
                "size": assessment.adjusted_size or 0.01,
                "stop_loss": None,
                "take_profit": None,
                "entry_price": price,
                "strategy_type": result.explanation.strategy_selected,
            })

        except Exception as exc:
            logger.debug("paper_entry_check_error", symbol=symbol, error=str(exc))
