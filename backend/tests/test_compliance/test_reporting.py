"""Tests for regulatory reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import json
import pytest

from forex_trading.shared.compliance.reporting import (
    ReportGenerator,
    Report,
    ReportSection,
    ReportType,
    ReportFormat,
    report_generator,
)


class TestReportDataClasses:
    """Tests for report data classes."""

    def test_report_section(self):
        section = ReportSection(
            title="Test Section",
            data=[{"key": "value"}],
            headers=["key"],
            summary={"count": 1},
        )
        assert section.title == "Test Section"
        assert section.data[0]["key"] == "value"

    def test_report_creation(self):
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="Daily P&L",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        assert report.report_type == ReportType.PNL_DAILY
        assert report.generated_at is not None

    def test_report_with_sections(self):
        report = Report(
            report_type=ReportType.BEST_EXECUTION,
            title="Best Execution",
            period_start=datetime.now(timezone.utc) - timedelta(days=30),
            period_end=datetime.now(timezone.utc),
        )
        report.sections.append(ReportSection(
            title="Summary",
            data={"metric": 100},
        ))
        assert len(report.sections) == 1


class TestReportGenerator:
    """Tests for the ReportGenerator."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator()

    @pytest.fixture
    def mock_db(self):
        mock = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        result.scalars.return_value.all.return_value = []
        mock.execute.return_value = result
        return mock

    def test_to_json(self, generator):
        """JSON export should produce valid JSON."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="Test Report",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        report.sections.append(ReportSection(
            title="Summary",
            data={"pnl": 1000.0},
        ))

        json_str = generator._to_json(report)
        parsed = json.loads(json_str)
        assert parsed["report_type"] == "pnl_daily"
        assert parsed["title"] == "Test Report"
        assert len(parsed["sections"]) == 1

    def test_to_csv(self, generator):
        """CSV export should produce CSV string."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="CSV Test",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        report.sections.append(ReportSection(
            title="Details",
            data=[{"symbol": "EURUSD", "pnl": 100}],
            headers=["symbol", "pnl"],
        ))

        csv_str = generator._to_csv(report)
        assert "CSV Test" in csv_str
        assert "EURUSD" in csv_str
        assert "pnl" in csv_str

    def test_to_html(self, generator):
        """HTML export should produce valid HTML."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="HTML Test",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        report.sections.append(ReportSection(
            title="Section 1",
            data={"key": "value"},
        ))

        html = generator._to_html(report)
        assert "<html>" in html
        assert "HTML Test" in html
        assert "Section 1" in html

    async def test_generate_pnl_report_empty(self, generator, mock_db):
        """PNL report with no data should generate empty sections."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        chain_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result, chain_result, chain_result]

        now = datetime.now(timezone.utc)
        report = await generator.generate_pnl_report(
            mock_db,
            period_start=now - timedelta(days=7),
            period_end=now,
            report_type=ReportType.PNL_WEEKLY,
        )
        assert report.report_type == ReportType.PNL_WEEKLY
        assert len(report.sections) >= 1

    async def test_generate_concentration_report(self, generator, mock_db):
        """Concentration report should handle empty positions."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        report = await generator.generate_concentration_report(mock_db)
        assert report.report_type == ReportType.POSITION_CONCENTRATION
        assert len(report.sections) >= 1

    async def test_generate_leverage_report(self, generator, mock_db):
        """Leverage report should handle empty risk states."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        report = await generator.generate_leverage_report(mock_db)
        assert report.report_type == ReportType.LEVERAGE_UTILIZATION

    async def test_generate_best_execution_report(self, generator, mock_db):
        """Best execution report should handle empty orders."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        now = datetime.now(timezone.utc)
        report = await generator.generate_best_execution_report(
            mock_db,
            period_start=now - timedelta(days=30),
            period_end=now,
        )
        assert report.report_type == ReportType.BEST_EXECUTION

    async def test_generate_risk_breach_report(self, generator, mock_db):
        """Risk breach report should handle empty alerts."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        report = await generator.generate_risk_breach_report(mock_db)
        assert report.report_type == ReportType.RISK_LIMIT_BREACH

    async def test_export_report_json(self, generator, mock_db):
        """Export as JSON should return JSON string."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="Export Test",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        result = await generator.export_report(mock_db, report, ReportFormat.JSON)
        parsed = json.loads(result)
        assert parsed["title"] == "Export Test"

    async def test_export_report_csv(self, generator, mock_db):
        """Export as CSV should return CSV string."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="CSV Export",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        result = await generator.export_report(mock_db, report, ReportFormat.CSV)
        assert "CSV Export" in result

    async def test_export_report_html_as_pdf_fallback(self, generator, mock_db):
        """PDF export without weasyprint should return HTML."""
        now = datetime.now(timezone.utc)
        report = Report(
            report_type=ReportType.PNL_DAILY,
            title="PDF Fallback",
            period_start=now - timedelta(days=1),
            period_end=now,
        )
        result = await generator.export_report(mock_db, report, ReportFormat.PDF)
        assert "<html>" in result


class TestGlobalReportGenerator:
    """Tests for the global report_generator instance."""

    def test_global_instance_exists(self):
        assert report_generator is not None
        assert isinstance(report_generator, ReportGenerator)
