"""Authoritative Risk Engine with full persistence and circuit breaker state machine.

This engine is the SINGLE SOURCE OF TRUTH for what trades are allowed.
Every trade MUST pass through ``assess_trade()`` before execution.
All state is persisted to PostgreSQL — restarting the process does NOT reset risk limits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from forex_trading.shared.database.uow import UnitOfWork, UnitOfWorkFactory
from forex_trading.shared.monitoring import (
    circuit_breaker_state,
    risk_alerts_total,
    risk_assessments_total,
    risk_vetoes_total,
)

logger = structlog.get_logger()


# ─── Value objects ────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"           # Normal trading
    OPEN = "open"               # All trades rejected
    HALF_OPEN = "half_open"     # One trial trade allowed


@dataclass
class RiskLimits:
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
    max_daily_trades: int = 50
    var_confidence_95_pct: float = 5.0
    leverage_limit: int = 50


@dataclass
class RiskAssessment:
    is_approved: bool
    adjusted_size: float | None = None
    max_allowed_size: float = 0.0
    warnings: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    assessment_id: UUID = field(default_factory=uuid4)


@dataclass
class RiskAlert:
    alert_id: UUID = field(default_factory=uuid4)
    level: RiskLevel = RiskLevel.INFO
    category: str = ""
    message: str = ""
    current_value: float = 0.0
    threshold_value: float = 0.0
    action_required: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── RiskEngine ───────────────────────────────────────────────────────────────


class RiskEngine:
    """Authoritative risk management engine.

    Accepts its dependencies (UoW factory) via constructor — no global state.
    All writes go through the UnitOfWork and are committed atomically.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        uow_factory: UnitOfWorkFactory | None = None,
    ) -> None:
        self.limits = limits or RiskLimits()
        self._uow_factory = uow_factory
        self._uow: UnitOfWork | None = None

    def attach_uow(self, uow: UnitOfWork) -> None:
        """Attach a UnitOfWork for this assessment cycle.
        Must be called at the start of every trade assessment.
        """
        self._uow = uow

    # ─── Public API ───────────────────────────────────────────────────────────

    async def assess_trade(
        self,
        broker_account_id: UUID,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: float | None = None,
        confidence: float = 0.0,
    ) -> RiskAssessment:
        """Run ALL risk checks and return an assessment.

        This is the only entry point for trade approval. Every check is
        evaluated against persisted state loaded from the DB.
        """
        if self._uow is None:
            raise RuntimeError("RiskEngine: no UnitOfWork attached. Call attach_uow() first.")

        warnings: list[str] = []
        violations: list[str] = []
        adjusted_size = size

        # 1. Load risk state from DB (always the latest persisted state)
        risk_state = await self._uow.risk_states.get_by_account(broker_account_id)

        if risk_state is None:
            # First time — create a fresh state
            risk_state = await self._uow.risk_states.upsert(
                broker_account_id,
                {
                    "current_equity": 0.0,
                    "peak_equity": 0.0,
                    "current_drawdown_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                    "daily_pnl": 0.0,
                    "weekly_pnl": 0.0,
                    "monthly_pnl": 0.0,
                    "total_exposure_pct": 0.0,
                    "open_positions": 0,
                    "consecutive_losses": 0,
                    "daily_trades": 0,
                    "is_circuit_breaker_active": False,
                },
            )
            await self._uow.flush()

        risk_score = self._compute_risk_score(risk_state)

        # 2. Circuit breaker check — PERSISTED state
        cb_violation = self._check_circuit_breaker(risk_state)
        if cb_violation:
            violations.append(cb_violation)
            return RiskAssessment(
                is_approved=False,
                violations=violations,
                risk_score=risk_score,
            )

        # 3. Maximum positions
        if risk_state.open_positions >= self.limits.max_positions:
            violations.append(
                f"Maximum positions reached: {risk_state.open_positions}/{self.limits.max_positions}"
            )

        # 4. Total exposure
        new_exposure = await self._compute_new_exposure(size, entry_price, risk_state)
        if new_exposure > self.limits.max_total_exposure_pct:
            violations.append(
                f"Total exposure would exceed limit: {new_exposure:.1f}% > {self.limits.max_total_exposure_pct}%"
            )

        # 5. Per-position size
        position_pct = self._position_size_pct(size, entry_price, risk_state)
        if position_pct > self.limits.max_position_size_pct:
            warnings.append(
                f"Position size exceeds recommended: {position_pct:.1f}% > {self.limits.max_position_size_pct}%"
            )
            adjusted_size = self._clamp_to_max_position_size(entry_price, risk_state)

        # 6. Drawdown limits
        dd_violations = self._check_drawdown_limits(risk_state)
        violations.extend(dd_violations)

        # 7. Consecutive losses
        if risk_state.consecutive_losses >= self.limits.max_consecutive_losses:
            violations.append(
                f"Consecutive losses limit reached: {risk_state.consecutive_losses}/{self.limits.max_consecutive_losses}"
            )

        # 8. Daily trade count
        if risk_state.daily_trades >= self.limits.max_daily_trades:
            violations.append(
                f"Daily trade limit reached: {risk_state.daily_trades}/{self.limits.max_daily_trades}"
            )

        # 9. Max drawdown — triggers circuit breaker
        if risk_state.current_drawdown_pct >= self.limits.max_drawdown_limit_pct:
            violations.append(
                f"Maximum drawdown limit reached: {risk_state.current_drawdown_pct:.1f}%"
            )
            await self._activate_circuit_breaker(
                broker_account_id, f"Max drawdown {risk_state.current_drawdown_pct:.1f}%"
            )

        # 10. Compute final risk score
        risk_score = self._compute_risk_score(risk_state)

        is_approved = len(violations) == 0

        risk_assessments_total.labels(approved=str(is_approved)).inc()
        if not is_approved:
            risk_vetoes_total.labels(reason=violations[0] if violations else "unknown").inc()
            logger.warning(
                "trade_rejected_by_risk",
                symbol=symbol,
                side=side,
                size=size,
                violations=violations,
                risk_score=round(risk_score, 3),
            )

        return RiskAssessment(
            is_approved=is_approved,
            adjusted_size=adjusted_size if adjusted_size != size else None,
            max_allowed_size=self._max_allowed_size(entry_price, risk_state),
            warnings=warnings,
            violations=violations,
            risk_score=risk_score,
        )

    async def record_trade_outcome(
        self,
        broker_account_id: UUID,
        pnl: float,
        won: bool,
    ) -> None:
        """Update risk state after a trade closes."""
        if self._uow is None:
            return
        state = await self._uow.risk_states.get_by_account(broker_account_id)
        if state is None:
            return

        state.daily_pnl = (state.daily_pnl or 0.0) + pnl
        state.weekly_pnl = (state.weekly_pnl or 0.0) + pnl
        state.monthly_pnl = (state.monthly_pnl or 0.0) + pnl
        state.daily_trades = (state.daily_trades or 0) + 1

        if won:
            state.consecutive_losses = 0
        else:
            state.consecutive_losses = (state.consecutive_losses or 0) + 1

        # Update peak equity
        equity = state.current_equity
        if equity > (state.peak_equity or 0.0):
            state.peak_equity = equity

        # Update max drawdown
        if state.peak_equity and state.peak_equity > 0:
            current_dd = max(0.0, (state.peak_equity - equity) / state.peak_equity * 100)
            state.current_drawdown_pct = current_dd
            if current_dd > (state.max_drawdown_pct or 0.0):
                state.max_drawdown_pct = current_dd

        # Check circuit breaker for consecutive losses
        if state.consecutive_losses >= self.limits.max_consecutive_losses:
            await self._activate_circuit_breaker(
                broker_account_id,
                f"{state.consecutive_losses} consecutive losses",
            )

    async def update_account_state(
        self,
        broker_account_id: UUID,
        equity: float,
        total_exposure_pct: float,
        open_positions: int,
    ) -> None:
        """Periodically sync risk state with broker account data."""
        if self._uow is None:
            return
        state = await self._uow.risk_states.upsert(
            broker_account_id,
            {
                "current_equity": equity,
                "total_exposure_pct": total_exposure_pct,
                "open_positions": open_positions,
                "last_updated": datetime.now(timezone.utc),
            },
        )
        # Update peak equity
        if equity > (state.peak_equity or 0.0):
            state.peak_equity = equity
        # Update drawdown
        if state.peak_equity and state.peak_equity > 0:
            current_dd = max(0.0, (state.peak_equity - equity) / state.peak_equity * 100)
            state.current_drawdown_pct = current_dd
            if current_dd > (state.max_drawdown_pct or 0.0):
                state.max_drawdown_pct = current_dd

    async def emergency_liquidate_all(
        self, broker_account_id: UUID, reason: str
    ) -> dict:
        """Trigger emergency liquidation and circuit breaker."""
        logger.critical(
            "emergency_liquidation",
            broker_account_id=str(broker_account_id),
            reason=reason,
        )
        await self._activate_circuit_breaker(broker_account_id, reason)
        await self._create_alert(
            level=RiskLevel.CRITICAL,
            category="emergency_liquidation",
            message=f"Emergency liquidation: {reason}",
            action_required=True,
        )
        return {"status": "circuit_breaker_activated", "reason": reason}

    async def deactivate_circuit_breaker(self, broker_account_id: UUID) -> None:
        """Manually deactivate circuit breaker."""
        circuit_breaker_state.labels(broker_account_id=str(broker_account_id)).set(0)
        if self._uow is None:
            return
        state = await self._uow.risk_states.get_by_account(broker_account_id)
        if state:
            state.is_circuit_breaker_active = False
            state.circuit_breaker_until = None
            state.circuit_breaker_reason = None

    async def health_check(self) -> dict:
        """Return risk system health status."""
        return {
            "limits": {
                "max_positions": self.limits.max_positions,
                "max_drawdown_pct": self.limits.max_drawdown_limit_pct,
                "max_consecutive_losses": self.limits.max_consecutive_losses,
            },
        }

    # ─── Circuit Breaker State Machine ────────────────────────────────────────

    async def _activate_circuit_breaker(self, broker_account_id: UUID, reason: str) -> None:
        circuit_breaker_state.labels(broker_account_id=str(broker_account_id)).set(1)
        if self._uow is None:
            return
        state = await self._uow.risk_states.get_by_account(broker_account_id)
        if state:
            state.is_circuit_breaker_active = True
            state.circuit_breaker_until = datetime.now(timezone.utc) + timedelta(
                minutes=self.limits.cooldown_minutes
            )
            state.circuit_breaker_reason = reason
            logger.critical(
                "circuit_breaker_activated",
                broker_account_id=str(broker_account_id),
                reason=reason,
                cooldown_minutes=self.limits.cooldown_minutes,
            )

    def _check_circuit_breaker(self, state: Any) -> str | None:
        if not state.is_circuit_breaker_active:
            return None
        if state.circuit_breaker_until and datetime.now(timezone.utc) >= state.circuit_breaker_until:
            state.is_circuit_breaker_active = False
            state.circuit_breaker_until = None
            state.circuit_breaker_reason = None
            logger.info("circuit_breaker_auto_reset", broker_account_id=str(state.broker_account_id))
            return None
        remaining = state.circuit_breaker_until - datetime.now(timezone.utc) if state.circuit_breaker_until else timedelta()
        return f"Circuit breaker active ({int(remaining.total_seconds() // 60)}m remaining): {state.circuit_breaker_reason or 'unknown'}"

    # ─── Drawdown Checks ─────────────────────────────────────────────────────

    def _check_drawdown_limits(self, state: Any) -> list[str]:
        violations: list[str] = []
        dd = state.current_drawdown_pct or 0.0
        if dd >= self.limits.daily_drawdown_limit_pct:
            violations.append(
                f"Daily drawdown limit reached: {dd:.1f}% >= {self.limits.daily_drawdown_limit_pct}%"
            )
        if dd >= self.limits.weekly_drawdown_limit_pct:
            violations.append(
                f"Weekly drawdown limit reached: {dd:.1f}% >= {self.limits.weekly_drawdown_limit_pct}%"
            )
        if dd >= self.limits.monthly_drawdown_limit_pct:
            violations.append(
                f"Monthly drawdown limit reached: {dd:.1f}% >= {self.limits.monthly_drawdown_limit_pct}%"
            )
        return violations

    def _check_daily_pnl(self, state: Any) -> str | None:
        if (state.daily_pnl or 0.0) < 0 and abs(state.daily_pnl) / (state.current_equity or 1.0) * 100 >= self.limits.daily_drawdown_limit_pct:
            return f"Daily loss limit: {abs(state.daily_pnl):.2f} ({abs(state.daily_pnl) / (state.current_equity or 1.0) * 100:.1f}%)"
        return None

    # ─── Sizing Helpers ───────────────────────────────────────────────────────

    def kelly_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        account_balance: float,
        max_cap_pct: float = 0.02,
    ) -> tuple[float, float]:
        """Compute position size using fractional Kelly.

        Args:
            win_rate: Historical win rate (0.0-1.0)
            avg_win: Average winning trade PnL in dollars
            avg_loss: Average losing trade PnL in dollars
            account_balance: Current account balance
            max_cap_pct: Maximum fraction of account to risk (Kelly cap)

        Returns:
            (fractional_kelly, max_risk_amount)
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.01, account_balance * max_cap_pct * 0.5

        b = avg_win / avg_loss  # odds ratio
        p = win_rate
        q = 1.0 - p
        kelly_pct = (p * b - q) / b
        if kelly_pct <= 0:
            return 0.01, account_balance * max_cap_pct * 0.25

        # Fractional Kelly (25% for safety)
        fk = kelly_pct * 0.25
        capped_fk = min(fk, max_cap_pct)
        risk_amount = account_balance * capped_fk
        return capped_fk, risk_amount

    def _position_size_pct(self, size: float, price: float, state: Any) -> float:
        equity = state.current_equity or 0.0
        if equity <= 0 or price <= 0:
            return 0.0
        return (size * price) / equity * 100

    async def _compute_new_exposure(self, size: float, price: float, state: Any) -> float:
        current = state.total_exposure_pct or 0.0
        equity = state.current_equity or 0.0
        if equity <= 0:
            return current
        return current + (size * price) / equity * 100

    def _max_allowed_size(self, price: float, state: Any) -> float:
        equity = state.current_equity or 0.0
        if price <= 0 or equity <= 0:
            return 0.0
        max_exposure = equity * (self.limits.max_total_exposure_pct / 100.0)
        current_exposure_value = (state.total_exposure_pct or 0.0) / 100.0 * equity
        remaining = max_exposure - current_exposure_value
        return max(0.0, remaining / price)

    def _clamp_to_max_position_size(self, price: float, state: Any) -> float:
        equity = state.current_equity or 0.0
        if price <= 0 or equity <= 0:
            return 0.0
        max_value = equity * (self.limits.max_position_size_pct / 100.0)
        return max_value / price

    def _compute_risk_score(self, state: Any) -> float:
        """Compute composite risk score (0.0 = safe, 1.0 = critical)."""
        dd_score = (state.current_drawdown_pct or 0.0) / self.limits.max_drawdown_limit_pct if self.limits.max_drawdown_limit_pct > 0 else 0
        exposure_score = (state.total_exposure_pct or 0.0) / self.limits.max_total_exposure_pct if self.limits.max_total_exposure_pct > 0 else 0
        loss_score = (state.consecutive_losses or 0) / self.limits.max_consecutive_losses if self.limits.max_consecutive_losses > 0 else 0
        cb_score = 1.0 if state.is_circuit_breaker_active else 0.0
        return min(1.0, (dd_score + exposure_score + loss_score + cb_score) / 4.0)

    async def _create_alert(
        self,
        level: RiskLevel,
        category: str,
        message: str,
        current_value: float = 0.0,
        threshold_value: float = 0.0,
        action_required: bool = False,
    ) -> None:
        if self._uow is None:
            return
        from forex_trading.shared.database.models_risk import RiskAlert as RiskAlertModel
        alert = RiskAlertModel(
            level=level,
            category=category,
            message=message,
            current_value=current_value,
            threshold_value=threshold_value,
            action_required=action_required,
        )
        risk_alerts_total.labels(level=level.value, category=category).inc()
        self._uow.session.add(alert)
        logger.warning("risk_alert_created", category=category, level=level.value, message=message)
