"""Exit Agent - evaluates trade exit conditions."""

from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
import structlog

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 20
_SWING_LOOKBACK = 5
_SESSION_END_BUFFER_MINUTES = 30  # exit this many minutes before session end


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _is_trail_stop_triggered(metadata: dict, current_price: float) -> tuple[bool, str]:
    """Check if the trailing stop has been triggered."""
    trail_stop = metadata.get("trail_stop_price")
    position_direction = metadata.get("position_direction", "")
    if trail_stop is None:
        return False, ""
    try:
        ts = float(trail_stop)
    except (TypeError, ValueError):
        return False, ""

    if position_direction in ("long", "buy") and current_price <= ts:
        return True, f"Trail stop triggered: price {current_price:.5f} <= trail_stop {ts:.5f}"
    if position_direction in ("short", "sell") and current_price >= ts:
        return True, f"Trail stop triggered: price {current_price:.5f} >= trail_stop {ts:.5f}"
    return False, ""


def _is_target_reached(metadata: dict, current_price: float) -> tuple[bool, str]:
    """Check if take-profit target is reached."""
    tp = metadata.get("take_profit_price")
    position_direction = metadata.get("position_direction", "")
    if tp is None:
        return False, ""
    try:
        tp_val = float(tp)
    except (TypeError, ValueError):
        return False, ""

    if position_direction in ("long", "buy") and current_price >= tp_val:
        return True, f"Take profit reached: price {current_price:.5f} >= TP {tp_val:.5f}"
    if position_direction in ("short", "sell") and current_price <= tp_val:
        return True, f"Take profit reached: price {current_price:.5f} <= TP {tp_val:.5f}"
    return False, ""


def _is_rr_achieved(metadata: dict, current_price: float) -> tuple[bool, str]:
    """Check if the desired R:R ratio has been achieved."""
    entry_price = metadata.get("entry_price")
    stop_price = metadata.get("stop_loss_price")
    target_rr = float(metadata.get("target_rr", 2.0))
    position_direction = metadata.get("position_direction", "")

    if entry_price is None or stop_price is None:
        return False, ""
    try:
        ep = float(entry_price)
        sp = float(stop_price)
    except (TypeError, ValueError):
        return False, ""

    risk = abs(ep - sp)
    if risk < 1e-8:
        return False, ""

    if position_direction in ("long", "buy"):
        reward = current_price - ep
    elif position_direction in ("short", "sell"):
        reward = ep - current_price
    else:
        return False, ""

    actual_rr = reward / risk
    if actual_rr >= target_rr:
        return True, f"R:R achieved: {actual_rr:.2f}x >= target {target_rr:.2f}x"
    return False, ""


def _is_session_ending(metadata: dict) -> tuple[bool, str]:
    """Check if the current trading session is about to end."""
    session_end = metadata.get("session_end_time")
    if session_end is None:
        return False, ""

    now = datetime.now(tz=timezone.utc)

    if isinstance(session_end, str):
        try:
            session_end = datetime.fromisoformat(session_end)
            if session_end.tzinfo is None:
                session_end = session_end.replace(tzinfo=timezone.utc)
        except ValueError:
            return False, ""
    elif isinstance(session_end, datetime):
        if session_end.tzinfo is None:
            session_end = session_end.replace(tzinfo=timezone.utc)
    else:
        return False, ""

    minutes_to_end = (session_end - now).total_seconds() / 60.0
    if 0 < minutes_to_end <= _SESSION_END_BUFFER_MINUTES:
        return True, f"Session ending in {minutes_to_end:.0f} min — close position"
    return False, ""


def _detect_reversal_pattern(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Detect if a reversal candlestick pattern is forming on the last 3 candles.

    Checks for bearish/bullish reversal: doji + direction change, or
    3 consecutive candles in opposite direction.
    Returns (is_reversal, description).
    """
    if len(df) < 3:
        return False, ""

    last3 = df.tail(3)
    closes = last3["close"].values
    opens = last3["open"].values
    highs = last3["high"].values
    lows = last3["low"].values

    # Check 3-candle reversal
    bull_run = all(closes[i] > opens[i] for i in range(3))
    bear_run = all(closes[i] < opens[i] for i in range(3))

    if bull_run:
        return True, "3 consecutive bullish candles — potential bearish reversal forming"
    if bear_run:
        return True, "3 consecutive bearish candles — potential bullish reversal forming"

    # Doji on last candle
    last_o = float(opens[-1])
    last_c = float(closes[-1])
    last_h = float(highs[-1])
    last_l = float(lows[-1])
    body = abs(last_c - last_o)
    full_range = last_h - last_l

    if full_range > 0 and body / full_range < 0.10:
        return True, f"Doji candle detected — indecision/potential reversal at {last_c:.5f}"

    return False, ""


def _get_position_direction(metadata: dict) -> str:
    """Extract current position direction from metadata."""
    return str(metadata.get("position_direction", "")).lower()


class ExitAgent(BaseAgent):
    """
    Evaluates optimal exit conditions for an open trade.

    Returns NEUTRAL to stay in the trade.
    Returns the OPPOSITE direction to signal exit.
    Checks: trail stop, target reached, R:R achieved, reversal pattern, session end.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="exit_ai", name="Exit Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles", "metadata"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return high weight in all regimes."""
        return 0.80

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Evaluate exit conditions and return a signal."""
        log = logger.bind(agent=self.agent_id, symbol=context.symbol)
        metadata = context.metadata or {}

        if len(context.candles) < _MIN_CANDLES:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning=f"Insufficient candles: {len(context.candles)} < {_MIN_CANDLES}",
            )

        df = _build_dataframe(context.candles)
        if len(df) < _MIN_CANDLES:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning="Candle data invalid after parsing",
            )

        price = float(df["close"].iloc[-1])
        pos_dir = _get_position_direction(metadata)

        # Determine what "exit" means directionally
        # If long → exit = SHORT signal; if short → exit = LONG signal
        if pos_dir in ("long", "buy"):
            exit_direction = SignalDirection.SHORT
        elif pos_dir in ("short", "sell"):
            exit_direction = SignalDirection.LONG
        else:
            exit_direction = SignalDirection.NEUTRAL  # no position — stay neutral

        exit_triggers: list[tuple[str, float]] = []

        trail_hit, trail_reason = _is_trail_stop_triggered(metadata, price)
        if trail_hit:
            exit_triggers.append((trail_reason, 0.95))

        target_hit, target_reason = _is_target_reached(metadata, price)
        if target_hit:
            exit_triggers.append((target_reason, 0.95))

        rr_hit, rr_reason = _is_rr_achieved(metadata, price)
        if rr_hit:
            exit_triggers.append((rr_reason, 0.85))

        session_end, session_reason = _is_session_ending(metadata)
        if session_end:
            exit_triggers.append((session_reason, 0.75))

        reversal_forming, reversal_reason = _detect_reversal_pattern(df)
        if reversal_forming:
            exit_triggers.append((reversal_reason, 0.65))

        if exit_triggers:
            max_conf = max(c for _, c in exit_triggers)
            reasons = "; ".join(r for r, _ in exit_triggers)
            direction = exit_direction if exit_direction != SignalDirection.NEUTRAL else SignalDirection.NEUTRAL

            log.info(
                "exit_signal",
                direction=direction.value,
                confidence=max_conf,
                triggers=len(exit_triggers),
            )

            return AgentSignal(
                agent_id=self.agent_id,
                direction=direction,
                confidence=max_conf,
                reasoning=f"EXIT triggered ({len(exit_triggers)} condition(s)): {reasons}",
                supporting_data={
                    "current_price": price,
                    "position_direction": pos_dir,
                    "triggers": [r for r, _ in exit_triggers],
                    "trigger_count": len(exit_triggers),
                },
            )

        # No exit condition met — stay in trade
        return AgentSignal(
            agent_id=self.agent_id,
            direction=SignalDirection.NEUTRAL,
            confidence=0.80,
            reasoning=f"No exit conditions met. Price={price:.5f}. Staying in trade.",
            supporting_data={
                "current_price": price,
                "position_direction": pos_dir,
                "trail_stop": metadata.get("trail_stop_price"),
                "take_profit": metadata.get("take_profit_price"),
            },
        )
