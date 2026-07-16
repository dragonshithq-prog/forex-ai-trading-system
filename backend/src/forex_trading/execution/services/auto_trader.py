"""Automated Trader — trend-responsive execution loop with full pipeline.

Pipeline per symbol:
  1. Fetch multi-timeframe candles
  2. Run trend analysis (EMA, ADX, RSI, MACD)
  3. If actionable trend → generate trade signal
  4. Size position via PositionSizer (fixed-fractional + Kelly)
  5. Validate via RiskEngine (circuit breaker, drawdown, exposure)
  6. Execute via PositionManager → ExecutionEngine saga
  7. Monitor open positions with trailing stops
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog

from forex_trading.ai.agents.base import MarketContext, SignalDirection
from forex_trading.broker.gateway import BrokerGateway
from forex_trading.execution.engine import ExecutionEngine
from forex_trading.execution.position_manager import PositionManager
from forex_trading.execution.services.position_sizer import PositionSizer
from forex_trading.execution.services.trend_monitor import TrendMonitor
from forex_trading.market_data.services.market_data_service import MarketDataService
from forex_trading.risk.engine import RiskEngine
from forex_trading.strategy.engine import StrategyEngine, TradeSignal, StrategyParameters

logger = structlog.get_logger()


class AutoTrader:
    """Automated trend-responsive trading system.

    Attach via DI container. Calls ``start(broker_connection_id)`` to begin.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        broker_gateway: BrokerGateway,
        risk_engine: RiskEngine,
        strategy_engine: StrategyEngine,
        execution_engine: ExecutionEngine,
        position_manager: PositionManager,
        position_sizer: PositionSizer,
        poll_interval_seconds: int = 60,
        symbols: list[str] | None = None,
    ) -> None:
        self._market_data = market_data
        self._broker_gateway = broker_gateway
        self._risk_engine = risk_engine
        self._strategy_engine = strategy_engine
        self._execution_engine = execution_engine
        self._position_manager = position_manager
        self._position_sizer = position_sizer

        self._trend_monitor = TrendMonitor(market_data)
        self._poll_interval = poll_interval_seconds
        self._symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY"]
        self._broker_connection_id: UUID | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, broker_connection_id: UUID) -> None:
        if self._running:
            logger.warning("auto_trader_already_running")
            return
        self._broker_connection_id = broker_connection_id
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "auto_trader_started",
            symbols=self._symbols,
            interval=self._poll_interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("auto_trader_stopped")

    async def execute_on_symbol(self, symbol: str) -> dict[str, Any]:
        """Run one full analysis-to-execution cycle for a single symbol."""
        result: dict[str, Any] = {"symbol": symbol, "action": "none"}

        prev = self._trend_monitor.get_last_snapshot(symbol)
        snapshot = await self._trend_monitor.analyze(symbol)
        result["trend"] = {
            "direction": snapshot.dominant_trend.value,
            "confidence": snapshot.confidence,
            "summary": snapshot.summary,
        }

        # Trend reversal — close opposing positions
        if prev is not None and self._broker_connection_id is not None:
            if prev.is_bullish and snapshot.is_bearish:
                result["reversal"] = "bullish_to_bearish"
                await self._close_positions_for_symbol(
                    symbol, "long", "trend reversed bullish→bearish"
                )
            elif prev.is_bearish and snapshot.is_bullish:
                result["reversal"] = "bearish_to_bullish"
                await self._close_positions_for_symbol(
                    symbol, "short", "trend reversed bearish→bullish"
                )

        if not snapshot.actionable:
            return result

        tick = await self._market_data.get_latest_tick(symbol)
        if tick is None:
            result["error"] = "No tick data available"
            return result

        entry_price = (tick["bid"] + tick["ask"]) / 2
        atr = await self._market_data.calculate_atr(symbol, "H1", 14)
        if atr <= 0:
            atr = 0.001

        sl_mult = 1.5
        tp_mult = 2.5

        if snapshot.dominant_trend == SignalDirection.LONG:
            stop_loss = entry_price - (atr * sl_mult)
            take_profit = entry_price + (atr * tp_mult)
        else:
            stop_loss = entry_price + (atr * sl_mult)
            take_profit = entry_price - (atr * tp_mult)

        # Get account info for position sizing
        account_info = None
        account_balance = 10000.0
        if self._broker_connection_id is not None:
            account_info = await self._broker_gateway.get_account_info(
                self._broker_connection_id
            )
            if account_info:
                account_balance = float(
                    getattr(account_info, "balance", account_info.get("balance", 10000))
                )

        # Size position using PositionSizer
        risk_pct = 1.0
        sizing = self._position_sizer.calculate_size(
            account_balance=account_balance,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            symbol=symbol,
        )
        lots = sizing.lots

        # Apply volatility adjustment
        hist_atr = await self._market_data.calculate_atr(symbol, "D1", 21)
        vol_ratio = (atr / hist_atr) if hist_atr > 0 else 1.0
        lots = self._position_sizer.risk_adjusted_size(lots, vol_ratio)

        result["sizing"] = {
            "lots": lots,
            "risk_amount": sizing.risk_amount,
            "risk_pct": sizing.risk_pct,
        }

        signal = TradeSignal(
            strategy=snapshot.regime_to_strategy_type(),
            symbol=symbol,
            direction=snapshot.dominant_trend,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=snapshot.confidence,
            parameters=StrategyParameters(
                stop_loss_pips=(atr * sl_mult) / 0.0001,
                take_profit_pips=(atr * tp_mult) / 0.0001,
                max_holding_time_minutes=240,
                metadata={
                    "atr": atr,
                    "lots": lots,
                    "current_spread_pips": (
                        tick.get("spread", 0) / 0.0001 if tick.get("spread") else 0
                    ),
                },
            ),
        )

        result["signal"] = {
            "direction": signal.direction.value,
            "entry": signal.entry_price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "confidence": signal.confidence,
        }

        if self._broker_connection_id is None:
            result["error"] = "No broker connection"
            return result

        exec_result = await self._execution_engine.process_signal(
            signal, self._broker_connection_id
        )

        result["execution"] = {
            "success": exec_result.success,
            "order_id": str(exec_result.order_id) if exec_result.order_id else None,
            "rejection": exec_result.rejection_reason,
        }

        if exec_result.success:
            result["action"] = "executed"
            logger.info(
                "auto_trade_executed",
                symbol=symbol,
                direction=snapshot.dominant_trend.value,
                lots=lots,
            )
        else:
            logger.info(
                "auto_trade_skipped",
                symbol=symbol,
                reason=exec_result.rejection_reason,
            )

        return result

    async def _close_positions_for_symbol(
        self, symbol: str, direction: str, reason: str
    ) -> None:
        if self._broker_connection_id is None:
            return
        try:
            positions = await self._broker_gateway.get_positions(
                self._broker_connection_id
            )
            for pos in positions:
                pos_side = getattr(pos, "side", getattr(pos, "direction", ""))
                if (
                    getattr(pos, "symbol", "").upper() == symbol.upper()
                    and pos_side == direction
                ):
                    pos_id = getattr(pos, "id", None)
                    if pos_id:
                        await self._execution_engine.close_position(pos_id, reason)
                    else:
                        # Close via broker gateway directly
                        await self._broker_gateway.close_position(
                            connection_id=self._broker_connection_id,
                            position_id=getattr(pos, "position_id", ""),
                        )
        except Exception as exc:
            logger.error(
                "close_positions_error", symbol=symbol, error=str(exc)
            )

    async def _run_loop(self) -> None:
        while self._running:
            try:
                for symbol in self._symbols:
                    if not self._running:
                        break
                    await self.execute_on_symbol(symbol)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("auto_trader_loop_error", error=str(exc))
            await asyncio.sleep(self._poll_interval)
