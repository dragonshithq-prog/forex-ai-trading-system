"""Risk Agent - evaluates spread, news risk, correlation and drawdown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 10
_MAX_SPREAD_PIPS = 3.0
_NEWS_WINDOW_MINUTES = 30  # avoid trading within 30 min of news
_MAX_DRAWDOWN_PCT = 5.0  # daily drawdown threshold
_MAX_CORRELATED_POSITIONS = 3


def _check_spread(metadata: dict) -> tuple[bool, str]:
    """Return (is_high, reason) for spread check."""
    spread = metadata.get("spread")
    if spread is None:
        return False, ""
    try:
        spread_val = float(spread)
    except (TypeError, ValueError):
        return False, ""
    if spread_val > _MAX_SPREAD_PIPS:
        return True, f"Spread {spread_val:.1f} pips exceeds max {_MAX_SPREAD_PIPS} pips"
    return False, ""


def _check_news_events(metadata: dict) -> tuple[bool, str]:
    """
    Return (is_risky, reason) based on upcoming high-impact news events.

    Expects metadata["news_events"] as list of dicts with 'time' (datetime or ISO str)
    and optionally 'impact' ('high'|'medium'|'low').
    """
    news_events = metadata.get("news_events", [])
    if not news_events:
        return False, ""

    now = datetime.now(tz=timezone.utc)
    window = timedelta(minutes=_NEWS_WINDOW_MINUTES)

    for event in news_events:
        if not isinstance(event, dict):
            continue
        impact = str(event.get("impact", "high")).lower()
        if impact not in ("high", "medium"):
            continue
        event_time = event.get("time")
        if event_time is None:
            continue
        if isinstance(event_time, str):
            try:
                event_time = datetime.fromisoformat(event_time)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        elif isinstance(event_time, datetime):
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        else:
            continue

        if abs(event_time - now) <= window:
            name = event.get("name", "unknown")
            minutes_away = (event_time - now).total_seconds() / 60.0
            return True, f"High-impact news '{name}' in {minutes_away:.0f} min"

    return False, ""


def _check_drawdown(metadata: dict) -> tuple[bool, str]:
    """Return (is_elevated, reason) for drawdown check."""
    drawdown = metadata.get("current_drawdown_pct")
    if drawdown is None:
        return False, ""
    try:
        dd_val = float(drawdown)
    except (TypeError, ValueError):
        return False, ""
    if dd_val >= _MAX_DRAWDOWN_PCT:
        return True, f"Current drawdown {dd_val:.1f}% >= max {_MAX_DRAWDOWN_PCT}%"
    return False, ""


def _check_correlation(metadata: dict) -> tuple[bool, str]:
    """Return (is_over_correlated, reason) for open positions check."""
    open_positions = metadata.get("open_positions", [])
    if not isinstance(open_positions, list):
        return False, ""
    if len(open_positions) >= _MAX_CORRELATED_POSITIONS:
        return True, f"{len(open_positions)} open positions — max correlated exposure reached"
    return False, ""


def _infer_market_direction(metadata: dict) -> SignalDirection:
    """
    Return the direction that the risk agent should pass through if risk is acceptable.

    Uses 'market_bias' key from metadata if set, otherwise NEUTRAL.
    """
    bias = metadata.get("market_bias", "neutral")
    if isinstance(bias, str):
        bias = bias.lower()
        if bias in ("long", "bullish", "buy"):
            return SignalDirection.LONG
        if bias in ("short", "bearish", "sell"):
            return SignalDirection.SHORT
    return SignalDirection.NEUTRAL


class RiskAgent(BaseAgent):
    """
    Evaluates the current risk environment before allowing a trade.

    Returns NEUTRAL (veto) if: spread is high, news is imminent, drawdown is elevated,
    or too many correlated positions exist. Otherwise, passes through market bias.
    High weight in all regimes — can veto other agents.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="risk_ai", name="Risk Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles", "metadata"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return high weight in all regimes — risk agent has veto power."""
        return 0.85

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Evaluate risk conditions and return signal."""
        log = logger.bind(agent=self.agent_id, symbol=context.symbol)
        metadata = context.metadata or {}

        red_flags: list[str] = []

        high_spread, spread_reason = _check_spread(metadata)
        if high_spread:
            red_flags.append(spread_reason)

        risky_news, news_reason = _check_news_events(metadata)
        if risky_news:
            red_flags.append(news_reason)

        elevated_dd, dd_reason = _check_drawdown(metadata)
        if elevated_dd:
            red_flags.append(dd_reason)

        over_correlated, corr_reason = _check_correlation(metadata)
        if over_correlated:
            red_flags.append(corr_reason)

        if red_flags:
            reason_str = "; ".join(red_flags)
            log.warning("risk_veto", flags=red_flags, symbol=context.symbol)
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.95,  # high confidence in the veto
                reasoning=f"RISK VETO: {reason_str}",
                supporting_data={
                    "red_flags": red_flags,
                    "spread": metadata.get("spread"),
                    "drawdown_pct": metadata.get("current_drawdown_pct"),
                    "open_positions": len(metadata.get("open_positions", [])),
                },
            )

        direction = _infer_market_direction(metadata)
        confidence = 0.70  # base pass-through confidence when risk is clean

        log.info("risk_clear", direction=direction.value, symbol=context.symbol)

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=(
                f"Risk environment acceptable: spread OK, no imminent news, "
                f"drawdown within limits, correlation within limits."
            ),
            supporting_data={
                "spread": metadata.get("spread"),
                "open_positions": len(metadata.get("open_positions", [])),
                "drawdown_pct": metadata.get("current_drawdown_pct"),
                "market_bias": metadata.get("market_bias"),
            },
        )
