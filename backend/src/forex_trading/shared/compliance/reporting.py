"""Regulatory Reporting — Generate compliance reports for regulators.

Supported report types:
  - P&L reports (daily, weekly, monthly)
  - Position concentration reports
  - Leverage utilization reports
  - Best execution reports (slippage analysis)
  - Risk limit breach reports

Reports can be exported to CSV, JSON, or PDF (via weasyprint if available).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_trading import (
    Order,
    Position,
    Deal,
    OrderStatus,
    PositionStatus,
)
from forex_trading.shared.database.models_risk import RiskAlert, RiskOverride, RiskLevel
from forex_trading.shared.database.models_compliance import RegulatoryReport
from forex_trading.shared.security.audit import audit_service

logger = logging.getLogger(__name__)


class ReportType(str, Enum):
    """Types of regulatory reports."""
    PNL_DAILY = "pnl_daily"
    PNL_WEEKLY = "pnl_weekly"
    PNL_MONTHLY = "pnl_monthly"
    POSITION_CONCENTRATION = "position_concentration"
    LEVERAGE_UTILIZATION = "leverage_utilization"
    BEST_EXECUTION = "best_execution"
    RISK_LIMIT_BREACH = "risk_limit_breach"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """Export formats for reports."""
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"


@dataclass
class ReportSection:
    """A section of a regulatory report."""
    title: str
    data: list[dict[str, Any]] | dict[str, Any]
    headers: list[str] | None = None
    summary: dict[str, Any] | None = None


@dataclass
class Report:
    """Complete regulatory report with metadata."""
    report_type: ReportType
    title: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sections: list[ReportSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    user_id: UUID | None = None


class ReportGenerator:
    """Generate regulatory compliance reports.

    Each report method returns a :class:`Report` object that can be
    exported to CSV, JSON, or PDF.
    """

    # ------------------------------------------------------------------
    # P&L Reports
    # ------------------------------------------------------------------

    async def generate_pnl_report(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime,
        report_type: ReportType = ReportType.PNL_DAILY,
        user_id: UUID | None = None,
    ) -> Report:
        """Generate a P&L report for the given period."""
        report = Report(
            report_type=report_type,
            title=f"P&L Report: {period_start.date()} to {period_end.date()}",
            period_start=period_start,
            period_end=period_end,
            user_id=user_id,
            metadata={"currency": "USD"},
        )

        # Fetch closed positions in period
        query = select(Position).where(
            Position.closed_at >= period_start,
            Position.closed_at <= period_end,
            Position.status == PositionStatus.CLOSED,
        ).order_by(Position.closed_at)

        result = await db.execute(query)
        positions = result.scalars().all()

        # Position-level P&L
        pnl_rows = []
        total_realized = 0.0
        total_unrealized = 0.0
        total_commission = 0.0
        total_swap = 0.0
        winning_trades = 0
        losing_trades = 0

        for pos in positions:
            pnl = pos.realized_pnl or 0.0
            gross_pnl = pnl + (pos.commission or 0.0) + (pos.swap or 0.0)
            total_realized += pnl
            total_commission += pos.commission or 0.0
            total_swap += pos.swap or 0.0

            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1

            pnl_rows.append({
                "position_id": str(pos.id),
                "symbol": pos.symbol,
                "side": pos.side.value if hasattr(pos.side, "value") else pos.side,
                "size": pos.size,
                "entry_price": pos.entry_price,
                "exit_price": pos.current_price,
                "realized_pnl": round(pnl, 2),
                "gross_pnl": round(gross_pnl, 2),
                "commission": round(pos.commission or 0, 2),
                "swap": round(pos.swap or 0, 2),
                "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
            })

        # Also get open positions for unrealized P&L
        result = await db.execute(
            select(Position).where(Position.status == PositionStatus.OPEN)
        )
        open_positions = result.scalars().all()
        for pos in open_positions:
            total_unrealized += pos.unrealized_pnl or 0.0

        total_trades = winning_trades + losing_trades

        report.sections.append(ReportSection(
            title="P&L Summary",
            data={
                "total_realized_pnl": round(total_realized, 2),
                "total_unrealized_pnl": round(total_unrealized, 2),
                "total_commission": round(total_commission, 2),
                "total_swap": round(total_swap, 2),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(winning_trades / total_trades, 4) if total_trades > 0 else 0,
                "net_pnl": round(total_realized - total_commission - total_swap, 2),
            },
        ))

        report.sections.append(ReportSection(
            title="Position Details",
            data=pnl_rows,
            headers=[
                "position_id", "symbol", "side", "size", "entry_price",
                "exit_price", "realized_pnl", "gross_pnl", "commission",
                "swap", "opened_at", "closed_at",
            ],
            summary={
                "total_realized_pnl": round(total_realized, 2),
                "total_positions": len(pnl_rows),
            },
        ))

        await self._save_report(db, report)
        return report

    # ------------------------------------------------------------------
    # Position Concentration Report
    # ------------------------------------------------------------------

    async def generate_concentration_report(
        self,
        db: AsyncSession,
        user_id: UUID | None = None,
    ) -> Report:
        """Generate a position concentration report."""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        report = Report(
            report_type=ReportType.POSITION_CONCENTRATION,
            title=f"Position Concentration Report: {week_ago.date()} to {now.date()}",
            period_start=week_ago,
            period_end=now,
            user_id=user_id,
        )

        # Open positions by symbol
        result = await db.execute(
            select(Position).where(Position.status == PositionStatus.OPEN)
        )
        open_positions = result.scalars().all()

        # Concentration by symbol
        symbol_exposure: dict[str, dict[str, Any]] = {}
        total_exposure = 0.0

        for pos in open_positions:
            sym = pos.symbol
            if sym not in symbol_exposure:
                symbol_exposure[sym] = {
                    "symbol": sym,
                    "total_size": 0.0,
                    "positions_count": 0,
                    "total_unrealized_pnl": 0.0,
                    "avg_entry_price": 0.0,
                    "sides": set(),
                }
            se = symbol_exposure[sym]
            se["total_size"] += pos.size
            se["positions_count"] += 1
            se["total_unrealized_pnl"] += pos.unrealized_pnl or 0.0
            se["sides"].add(pos.side.value if hasattr(pos.side, "value") else pos.side)

        total_exposure = sum(s["total_size"] for s in symbol_exposure.values())

        concentration_rows = []
        for sym, data in symbol_exposure.items():
            pct = round((data["total_size"] / total_exposure * 100), 2) if total_exposure > 0 else 0
            concentration_rows.append({
                "symbol": sym,
                "total_size": round(data["total_size"], 4),
                "positions_count": data["positions_count"],
                "sides": ", ".join(sorted(data["sides"])),
                "total_unrealized_pnl": round(data["total_unrealized_pnl"], 2),
                "exposure_pct": pct,
            })

        concentration_rows.sort(key=lambda r: r["exposure_pct"], reverse=True)

        report.sections.append(ReportSection(
            title="Position Concentration by Symbol",
            data=concentration_rows,
            headers=["symbol", "total_size", "positions_count", "sides",
                     "total_unrealized_pnl", "exposure_pct"],
            summary={
                "total_exposure": round(total_exposure, 4),
                "total_symbols": len(concentration_rows),
                "highest_concentration": concentration_rows[0]
                if concentration_rows else None,
            },
        ))

        await self._save_report(db, report)
        return report

    # ------------------------------------------------------------------
    # Leverage Utilization Report
    # ------------------------------------------------------------------

    async def generate_leverage_report(
        self,
        db: AsyncSession,
        user_id: UUID | None = None,
    ) -> Report:
        """Generate a leverage utilization report."""
        now = datetime.now(timezone.utc)
        month_ago = now - timedelta(days=30)

        report = Report(
            report_type=ReportType.LEVERAGE_UTILIZATION,
            title=f"Leverage Utilization Report: {month_ago.date()} to {now.date()}",
            period_start=month_ago,
            period_end=now,
            user_id=user_id,
        )

        # Get risk states for leverage info
        from forex_trading.shared.database.models_risk import RiskState
        result = await db.execute(select(RiskState))
        risk_states = result.scalars().all()

        leverage_rows = []
        for rs in risk_states:
            total_exposure_pct = rs.total_exposure_pct or 0
            equity = rs.current_equity or 1
            used_margin = equity * (total_exposure_pct / 100) if total_exposure_pct > 0 else 0
            leverage_ratio = round(total_exposure_pct, 2)

            leverage_rows.append({
                "broker_account_id": str(rs.broker_account_id),
                "equity": round(equity, 2),
                "total_exposure_pct": round(total_exposure_pct, 2),
                "used_margin": round(used_margin, 2),
                "leverage_ratio": leverage_ratio,
                "current_drawdown_pct": round(rs.current_drawdown_pct, 2),
                "open_positions": rs.open_positions,
                "is_circuit_breaker_active": rs.is_circuit_breaker_active,
            })

        report.sections.append(ReportSection(
            title="Leverage Utilization",
            data=leverage_rows,
            headers=["broker_account_id", "equity", "total_exposure_pct",
                     "used_margin", "leverage_ratio", "current_drawdown_pct",
                     "open_positions", "is_circuit_breaker_active"],
            summary={
                "total_accounts": len(leverage_rows),
                "avg_leverage": round(
                    sum(r["leverage_ratio"] for r in leverage_rows) / len(leverage_rows), 2
                ) if leverage_rows else 0,
                "max_leverage": round(
                    max(r["leverage_ratio"] for r in leverage_rows), 2
                ) if leverage_rows else 0,
            },
        ))

        await self._save_report(db, report)
        return report

    # ------------------------------------------------------------------
    # Best Execution Report
    # ------------------------------------------------------------------

    async def generate_best_execution_report(
        self,
        db: AsyncSession,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        user_id: UUID | None = None,
    ) -> Report:
        """Generate a best execution report (slippage analysis)."""
        now = datetime.now(timezone.utc)
        period_start = period_start or (now - timedelta(days=30))
        period_end = period_end or now

        report = Report(
            report_type=ReportType.BEST_EXECUTION,
            title=f"Best Execution Report: {period_start.date()} to {period_end.date()}",
            period_start=period_start,
            period_end=period_end,
            user_id=user_id,
        )

        # Filled orders with slippage data
        result = await db.execute(
            select(Order).where(
                Order.filled_at >= period_start,
                Order.filled_at <= period_end,
                Order.status == OrderStatus.FILLED,
            ).order_by(Order.filled_at)
        )
        orders = result.scalars().all()

        execution_rows = []
        total_slippage = 0.0
        total_orders = len(orders)
        positive_slippage = 0
        negative_slippage = 0
        zero_slippage = 0

        for order in orders:
            slip = order.slippage or 0.0
            total_slippage += slip

            if slip > 0:
                positive_slippage += 1
            elif slip < 0:
                negative_slippage += 1
            else:
                zero_slippage += 1

            execution_rows.append({
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, "value") else order.side,
                "quantity": order.filled_quantity,
                "expected_price": order.price,
                "filled_price": order.filled_price,
                "slippage": round(slip, 4),
                "commission": round(order.commission, 2),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
            })

        report.sections.append(ReportSection(
            title="Execution Quality Summary",
            data={
                "total_orders": total_orders,
                "total_slippage": round(total_slippage, 4),
                "avg_slippage": round(
                    total_slippage / total_orders, 4
                ) if total_orders > 0 else 0,
                "orders_with_positive_slippage": positive_slippage,
                "orders_with_negative_slippage": negative_slippage,
                "orders_with_zero_slippage": zero_slippage,
                "positive_slippage_pct": round(
                    positive_slippage / total_orders * 100, 2
                ) if total_orders > 0 else 0,
            },
        ))

        report.sections.append(ReportSection(
            title="Order Execution Details",
            data=execution_rows,
            headers=["order_id", "symbol", "side", "quantity", "expected_price",
                     "filled_price", "slippage", "commission", "filled_at"],
            summary={
                "avg_slippage": round(
                    total_slippage / total_orders, 4
                ) if total_orders > 0 else 0,
            },
        ))

        await self._save_report(db, report)
        return report

    # ------------------------------------------------------------------
    # Risk Limit Breach Report
    # ------------------------------------------------------------------

    async def generate_risk_breach_report(
        self,
        db: AsyncSession,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        user_id: UUID | None = None,
    ) -> Report:
        """Generate a report on risk limit breaches."""
        now = datetime.now(timezone.utc)
        period_start = period_start or (now - timedelta(days=30))
        period_end = period_end or now

        report = Report(
            report_type=ReportType.RISK_LIMIT_BREACH,
            title=f"Risk Limit Breach Report: {period_start.date()} to {period_end.date()}",
            period_start=period_start,
            period_end=period_end,
            user_id=user_id,
        )

        # Critical risk alerts
        result = await db.execute(
            select(RiskAlert).where(
                RiskAlert.created_at >= period_start,
                RiskAlert.created_at <= period_end,
                RiskAlert.level.in_([RiskLevel.WARNING, RiskLevel.CRITICAL]),
            ).order_by(RiskAlert.created_at.desc())
        )
        alerts = result.scalars().all()

        breach_rows = []
        for alert in alerts:
            breach_rows.append({
                "alert_id": str(alert.id),
                "level": alert.level.value if hasattr(alert.level, "value") else alert.level,
                "category": alert.category,
                "message": alert.message,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value,
                "action_required": alert.action_required,
                "acknowledged": alert.acknowledged,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            })

        # Risk overrides
        result = await db.execute(
            select(RiskOverride).where(
                RiskOverride.created_at >= period_start,
                RiskOverride.created_at <= period_end,
            ).order_by(RiskOverride.created_at.desc())
        )
        overrides = result.scalars().all()

        override_rows = []
        for ovr in overrides:
            override_rows.append({
                "override_id": str(ovr.id),
                "action": ovr.action.value if hasattr(ovr.action, "value") else ovr.action,
                "reason": ovr.reason,
                "created_at": ovr.created_at.isoformat() if ovr.created_at else None,
            })

        report.sections.append(ReportSection(
            title="Risk Alert Breaches",
            data=breach_rows,
            headers=["alert_id", "level", "category", "message", "current_value",
                     "threshold_value", "action_required", "acknowledged", "created_at"],
            summary={
                "total_alerts": len(breach_rows),
                "critical_alerts": sum(1 for r in breach_rows if r["level"] == "critical"),
                "warning_alerts": sum(1 for r in breach_rows if r["level"] == "warning"),
            },
        ))

        report.sections.append(ReportSection(
            title="Risk Overrides",
            data=override_rows,
            headers=["override_id", "action", "reason", "created_at"],
            summary={"total_overrides": len(override_rows)},
        ))

        await self._save_report(db, report)
        return report

    # ------------------------------------------------------------------
    # Export Methods
    # ------------------------------------------------------------------

    async def export_report(
        self,
        db: AsyncSession,
        report: Report,
        fmt: ReportFormat = ReportFormat.JSON,
    ) -> str:
        """Export a report to the specified format."""
        if fmt == ReportFormat.JSON:
            return self._to_json(report)
        elif fmt == ReportFormat.CSV:
            return self._to_csv(report)
        elif fmt == ReportFormat.PDF:
            return await self._to_pdf(report)
        raise ValueError(f"Unsupported format: {fmt}")

    def _to_json(self, report: Report) -> str:
        """Serialize report to JSON."""
        data = {
            "report_type": report.report_type.value,
            "title": report.title,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "metadata": report.metadata,
            "sections": [],
        }
        for section in report.sections:
            section_data = {
                "title": section.title,
                "data": section.data,
                "headers": section.headers,
                "summary": section.summary,
            }
            data["sections"].append(section_data)
        return json.dumps(data, indent=2, default=str)

    def _to_csv(self, report: Report) -> str:
        """Serialize the first data section to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["Report", report.title])
        writer.writerow(["Period", f"{report.period_start.date()} to {report.period_end.date()}"])
        writer.writerow(["Generated", report.generated_at.isoformat()])
        writer.writerow([])

        for section in report.sections:
            writer.writerow([section.title])
            if isinstance(section.data, list) and section.data:
                if section.headers:
                    writer.writerow(section.headers)
                else:
                    writer.writerow(section.data[0].keys())
                for row in section.data:
                    writer.writerow(row.values())
            elif isinstance(section.data, dict):
                for key, value in section.data.items():
                    writer.writerow([key, value])
            writer.writerow([])

            if section.summary:
                writer.writerow(["Summary"])
                for key, value in section.summary.items():
                    writer.writerow([key, value])
                writer.writerow([])

        return output.getvalue()

    async def _to_pdf(self, report: Report) -> str:
        """Generate a PDF report.

        Uses weasyprint if available, otherwise falls back to HTML.
        """
        try:
            from weasyprint import HTML
            html = self._to_html(report)
            pdf_buffer = io.BytesIO()
            HTML(string=html).write_pdf(pdf_buffer)
            return pdf_buffer.getvalue().decode("latin-1")
        except ImportError:
            logger.warning("weasyprint not available, returning HTML instead of PDF")
            return self._to_html(report)

    def _to_html(self, report: Report) -> str:
        """Convert report to HTML string."""
        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{report.title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; }}
    h1 {{ color: #333; }}
    h2 {{ color: #555; margin-top: 30px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background-color: #f2f2f2; }}
    .summary {{ background-color: #e7f3fe; padding: 10px; border-radius: 5px; }}
    .meta {{ color: #888; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>{report.title}</h1>
  <p class="meta">Period: {report.period_start.date()} to {report.period_end.date()}</p>
  <p class="meta">Generated: {report.generated_at.isoformat()}</p>
"""
        for section in report.sections:
            html += f"<h2>{section.title}</h2>\n"

            if isinstance(section.data, dict):
                html += '<table>\n'
                for key, value in section.data.items():
                    html += f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>\n"
                html += '</table>\n'
            elif isinstance(section.data, list) and section.data:
                headers = section.headers or list(section.data[0].keys())
                html += '<table>\n<thead><tr>'
                for h in headers:
                    html += f"<th>{h}</th>"
                html += '</tr></thead>\n<tbody>\n'
                for row in section.data:
                    html += '<tr>'
                    for h in headers:
                        html += f"<td>{row.get(h, '')}</td>"
                    html += '</tr>\n'
                html += '</tbody>\n</table>\n'

            if section.summary:
                html += '<div class="summary">\n'
                for key, value in section.summary.items():
                    html += f"<p><strong>{key}:</strong> {value}</p>\n"
                html += '</div>\n'

        html += '</body>\n</html>'
        return html

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save_report(
        self,
        db: AsyncSession,
        report: Report,
    ) -> RegulatoryReport:
        """Save report metadata to the database."""
        db_report = RegulatoryReport(
            user_id=report.user_id,
            report_type=report.report_type.value,
            report_format="json",
            period_start=report.period_start,
            period_end=report.period_end,
            parameters=report.metadata,
        )
        db.add(db_report)
        await db.commit()
        await db.refresh(db_report)

        # Audit the report generation
        await audit_service.record(
            db,
            user_id=report.user_id,
            action="compliance.reporting.generate",
            resource_type="regulatory_report",
            resource_id=str(db_report.id),
            details={
                "report_type": report.report_type.value,
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
            },
            ip_address=None,
        )

        return db_report


# Global default report generator
report_generator = ReportGenerator()
