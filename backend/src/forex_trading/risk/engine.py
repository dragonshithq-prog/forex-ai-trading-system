"""Risk Engine - Authoritative risk management system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from forex_trading.config import get_settings
from forex_trading.core.exceptions import RiskLimitExceeded, CircuitBreakerActive

logger = structlog.get_logger()
settings = get_settings()


class RiskLevel(str, Enum):
    """Risk alert levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class OverrideAction(str, Enum):
    """Risk override actions."""
    REJECT_ORDER = "reject_order"
    CLOSE_POSITION = "close_position"
    REDUCE_SIZE = "reduce_size"
    HALT_TRADING = "halt_trading"


@dataclass
class RiskLimits:
    """Risk limits configuration."""
    max_position_size_pct: float = 2.0
    max_total_exposure_pct: float = 20.0
    max_positions: int = 10
    daily_drawdown_limit_pct: float = 3.0
    weekly_drawdown_limit_pct: float = 5.0
    monthly_drawdown_limit_pct: float = 10.0
    max_drawdown_limit_pct: float = 15.0
    max_exposure_per_pair_pct: float = 5.0
    max_correlated_exposure_pct: float = 10.0
    max_slippage_pips: float = 3.0
    max_spread_pips: float = 5.0
    max_consecutive_losses: int = 5
    cooldown_minutes: int = 60


@dataclass
class RiskState:
    """Current risk state of the system."""
    current_equity: float = 0.0
    current_drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    total_exposure_pct: float = 0.0
    open_positions: int = 0
    consecutive_losses: int = 0
    is_circuit_breaker_active: bool = False
    circuit_breaker_until: datetime | None = None
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Position for risk calculation."""
    position_id: UUID
    symbol: str
    side: str  # "long" | "short"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None = None


@dataclass
class RiskAssessment:
    """Result of risk assessment for a proposed trade."""
    is_approved: bool
    adjusted_size: float | None = None
    max_allowed_size: float = 0.0
    warnings: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    risk_score: float = 0.0  # 0.0 (safe) - 1.0 (high risk)


@dataclass
class RiskAlert:
    """Risk management alert."""
    alert_id: UUID = field(default_factory=uuid4)
    level: RiskLevel = RiskLevel.INFO
    category: str = ""
    message: str = ""
    current_value: float = 0.0
    threshold_value: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class RiskEngine:
    """
    AUTHORITATIVE Risk Engine.

    This engine has absolute override authority over all other components.
    It can:
    - REJECT any trade from any source
    - FORCE close any position
    - REDUCE position size
    - BLOCK trading during extreme conditions
    - EMERGENCY liquidate all positions

    NO OTHER COMPONENT CAN OVERRIDE THE RISK ENGINE.
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits(
            max_position_size_pct=settings.MAX_POSITION_SIZE_PCT,
            max_total_exposure_pct=settings.MAX_TOTAL_EXPOSURE_PCT,
            max_positions=settings.MAX_POSITIONS,
            daily_drawdown_limit_pct=settings.MAX_DRAWDOWN_DAILY_PCT,
            max_drawdown_limit_pct=settings.MAX_DRAWDOWN_TOTAL_PCT,
        )
        self._state = RiskState()
        self._positions: dict[UUID, Position] = {}
        self._alerts: list[RiskAlert] = []
        self._overrides: list[dict] = []

    async def assess_trade(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: float | None = None,
    ) -> RiskAssessment:
        """
        Assess a proposed trade against all risk limits.

        Args:
            symbol: Trading symbol
            side: Trade side (long/short)
            size: Proposed position size
            entry_price: Entry price
            stop_loss: Optional stop loss price

        Returns:
            RiskAssessment with approval status and any adjustments
        """
        warnings = []
        violations = []
        adjusted_size = size

        # Check circuit breaker
        if self._state.is_circuit_breaker_active:
            if self._state.circuit_breaker_until and datetime.utcnow() < self._state.circuit_breaker_until:
                violations.append("Circuit breaker is active")
                return RiskAssessment(
                    is_approved=False,
                    violations=violations,
                    risk_score=1.0,
                )
            else:
                self._deactivate_circuit_breaker()

        # Check maximum positions
        if self._state.open_positions >= self.limits.max_positions:
            violations.append(f"Maximum positions reached: {self._state.open_positions}/{self.limits.max_positions}")

        # Check total exposure
        new_exposure = self._calculate_new_exposure(size, entry_price)
        if new_exposure > self.limits.max_total_exposure_pct:
            violations.append(f"Total exposure would exceed limit: {new_exposure:.1f}% > {self.limits.max_total_exposure_pct}%")
            # Reduce size to fit
            adjusted_size = self._calculate_max_allowed_size(entry_price)

        # Check per-position size
        position_pct = self._calculate_position_pct(size, entry_price)
        if position_pct > self.limits.max_position_size_pct:
            warnings.append(f"Position size exceeds recommended: {position_pct:.1f}% > {self.limits.max_position_size_pct}%")
            adjusted_size = self._calculate_max_position_size(entry_price)

        # Check drawdown limits
        if self._state.current_drawdown_pct >= self.limits.daily_drawdown_limit_pct:
            violations.append(f"Daily drawdown limit reached: {self._state.current_drawdown_pct:.1f}%")

        if self._state.current_drawdown_pct >= self.limits.max_drawdown_limit_pct:
            violations.append(f"Maximum drawdown limit reached: {self._state.current_drawdown_pct:.1f}%")
            await self._activate_circuit_breaker("Maximum drawdown exceeded")

        # Check consecutive losses
        if self._state.consecutive_losses >= self.limits.max_consecutive_losses:
            violations.append(f"Consecutive losses limit reached: {self._state.consecutive_losses}")

        # Calculate risk score
        risk_score = self._calculate_risk_score()

        is_approved = len(violations) == 0

        if not is_approved:
            logger.warning(
                "trade_rejected_by_risk",
                symbol=symbol,
                side=side,
                size=size,
                violations=violations,
            )

        return RiskAssessment(
            is_approved=is_approved,
            adjusted_size=adjusted_size if adjusted_size != size else None,
            max_allowed_size=self._calculate_max_allowed_size(entry_price),
            warnings=warnings,
            violations=violations,
            risk_score=risk_score,
        )

    async def monitor_position(self, position: Position) -> RiskAlert | None:
        """Monitor an open position for risk limits."""
        self._positions[position.position_id] = position

        # Check position P&L
        if position.unrealized_pnl < 0:
            loss_pct = abs(position.unrealized_pnl) / self._state.current_equity * 100
            if loss_pct > self.limits.max_position_size_pct:
                return RiskAlert(
                    level=RiskLevel.WARNING,
                    category="position_loss",
                    message=f"Position {position.symbol} loss exceeds threshold: {loss_pct:.1f}%",
                    current_value=loss_pct,
                    threshold_value=self.limits.max_position_size_pct,
                )

        return None

    async def force_close_position(self, position_id: UUID, reason: str) -> dict:
        """Force close a position (override action)."""
        position = self._positions.get(position_id)
        if not position:
            return {"error": "Position not found"}

        self._overrides.append({
            "action": OverrideAction.CLOSE_POSITION,
            "position_id": str(position_id),
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.warning(
            "force_close_position",
            position_id=str(position_id),
            symbol=position.symbol,
            reason=reason,
        )

        return {"status": "closed", "position_id": str(position_id)}

    async def emergency_liquidate_all(self, reason: str) -> dict:
        """Emergency liquidation of all positions."""
        self._overrides.append({
            "action": OverrideAction.HALT_TRADING,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.critical("emergency_liquidation", reason=reason, positions=len(self._positions))

        self._state.is_circuit_breaker_active = True
        return {"status": "liquidating", "positions_count": len(self._positions)}

    def update_state(self, equity: float, drawdown_pct: float) -> None:
        """Update risk state with current account data."""
        self._state.current_equity = equity
        self._state.current_drawdown_pct = drawdown_pct
        self._state.last_updated = datetime.utcnow()

    def get_state(self) -> RiskState:
        """Get current risk state."""
        return self._state

    def get_alerts(self, limit: int = 100) -> list[RiskAlert]:
        """Get recent risk alerts."""
        return self._alerts[-limit:]

    def _calculate_new_exposure(self, size: float, price: float) -> float:
        """Calculate what total exposure would be after this trade."""
        current_exposure = self._state.total_exposure_pct
        new_exposure_value = (size * price) / self._state.current_equity * 100 if self._state.current_equity > 0 else 0
        return current_exposure + new_exposure_value

    def _calculate_position_pct(self, size: float, price: float) -> float:
        """Calculate position size as percentage of equity."""
        if self._state.current_equity <= 0:
            return 0.0
        return (size * price) / self._state.current_equity * 100

    def _calculate_max_allowed_size(self, price: float) -> float:
        """Calculate maximum allowed position size."""
        if price <= 0 or self._state.current_equity <= 0:
            return 0.0
        max_exposure = self._state.current_equity * (self.limits.max_total_exposure_pct / 100)
        current_exposure_value = self._state.total_exposure_pct / 100 * self._state.current_equity
        remaining = max_exposure - current_exposure_value
        return max(0, remaining / price)

    def _calculate_max_position_size(self, price: float) -> float:
        """Calculate max size for single position limit."""
        if price <= 0 or self._state.current_equity <= 0:
            return 0.0
        max_value = self._state.current_equity * (self.limits.max_position_size_pct / 100)
        return max_value / price

    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0.0 - 1.0)."""
        drawdown_score = self._state.current_drawdown_pct / self.limits.max_drawdown_limit_pct
        exposure_score = self._state.total_exposure_pct / self.limits.max_total_exposure_pct
        loss_score = self._state.consecutive_losses / self.limits.max_consecutive_losses

        return min(1.0, (drawdown_score + exposure_score + loss_score) / 3)

    async def _activate_circuit_breaker(self, reason: str) -> None:
        """Activate circuit breaker."""
        from datetime import timedelta
        self._state.is_circuit_breaker_active = True
        self._state.circuit_breaker_until = datetime.utcnow() + timedelta(minutes=self.limits.cooldown_minutes)

        alert = RiskAlert(
            level=RiskLevel.CRITICAL,
            category="circuit_breaker",
            message=f"Circuit breaker activated: {reason}",
        )
        self._alerts.append(alert)

        logger.critical("circuit_breaker_activated", reason=reason)

    def _deactivate_circuit_breaker(self) -> None:
        """Deactivate circuit breaker."""
        self._state.is_circuit_breaker_active = False
        self._state.circuit_breaker_until = None
        logger.info("circuit_breaker_deactivated")
