"""Tests for risk disclosure generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.compliance.disclosure import (
    RiskDisclosureGenerator,
    Jurisdiction,
    risk_disclosure_generator,
)


class TestJurisdiction:
    """Tests for the Jurisdiction enum."""

    def test_jurisdictions_exist(self):
        assert Jurisdiction.GLOBAL.value == "global"
        assert Jurisdiction.EU.value == "eu"
        assert Jurisdiction.US.value == "us"
        assert Jurisdiction.UK.value == "uk"


class TestRiskDisclosureGenerator:
    """Tests for the RiskDisclosureGenerator."""

    @pytest.fixture
    def generator(self):
        return RiskDisclosureGenerator()

    @pytest.fixture
    def mock_db(self):
        mock = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        result.scalars.return_value.all.return_value = []
        mock.execute.return_value = result
        return mock

    async def test_generate_general_disclaimer(self, generator, mock_db):
        """General disclaimer should include risk warning text."""
        disclosure = await generator.generate_general_disclaimer(
            mock_db,
            jurisdiction=Jurisdiction.GLOBAL,
            language="en",
        )
        assert disclosure.disclosure_type == "general"
        assert disclosure.jurisdiction == "global"
        assert "RISK" in disclosure.content
        assert "leverage" in disclosure.content.lower()

    async def test_generate_eu_disclaimer(self, generator, mock_db):
        """EU disclaimer should include ESMA warning."""
        disclosure = await generator.generate_general_disclaimer(
            mock_db,
            jurisdiction=Jurisdiction.EU,
        )
        assert disclosure.jurisdiction == "eu"
        assert "ESMA" in disclosure.content or "74-89%" in disclosure.content

    async def test_generate_us_disclaimer(self, generator, mock_db):
        """US disclaimer should include CFTC notice."""
        disclosure = await generator.generate_general_disclaimer(
            mock_db,
            jurisdiction=Jurisdiction.US,
        )
        assert disclosure.jurisdiction == "us"
        assert "CFTC" in disclosure.content

    async def test_generate_strategy_warning(self, generator, mock_db):
        """Strategy warning should include strategy-specific risks."""
        disclosure = await generator.generate_strategy_warning(
            mock_db,
            strategy_type="trend_following",
            jurisdiction=Jurisdiction.GLOBAL,
        )
        assert "trend_following" in disclosure.disclosure_type
        assert "trending" in disclosure.content.lower()

    async def test_generate_strategy_warning_unknown(self, generator, mock_db):
        """Unknown strategy type should use generic warning."""
        disclosure = await generator.generate_strategy_warning(
            mock_db,
            strategy_type="unknown_strategy",
        )
        assert "unknown_strategy" in disclosure.disclosure_type

    async def test_generate_per_trade_acknowledgment(self, generator, mock_db):
        """Per-trade acknowledgment should include trade details."""
        disclosure = await generator.generate_per_trade_acknowledgment(
            mock_db,
            user_id=uuid4(),
            order_id=uuid4(),
            symbol="EURUSD",
            side="buy",
            quantity=0.1,
            leverage=100,
        )
        assert "per_trade" in disclosure.disclosure_type
        assert "EURUSD" in disclosure.content
        assert "100:1" in disclosure.content or "leverage" in disclosure.content.lower()

    async def test_acknowledge_disclosure(self, generator, mock_db):
        """Acknowledging disclosure should update the record."""
        mock_disclosure = MagicMock()
        mock_disclosure.acknowledged = False
        mock_disclosure.acknowledged_at = None
        mock_disclosure.disclosure_type = "general"
        mock_disclosure.version = "1.0.0"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_disclosure

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        chain_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result, chain_result]

        result = await generator.acknowledge_disclosure(
            mock_db, uuid4(), uuid4(),
        )
        assert result is not None

    async def test_acknowledge_nonexistent(self, generator, mock_db):
        """Acknowledging non-existent disclosure should return None."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await generator.acknowledge_disclosure(
            mock_db, uuid4(), uuid4(),
        )
        assert result is None

    async def test_get_user_disclosures(self, generator, mock_db):
        """Get user disclosures should return formatted list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        disclosures = await generator.get_user_disclosures(mock_db, uuid4())
        assert isinstance(disclosures, list)

    def test_get_strategy_warning(self, generator):
        """Get strategy warning should return known warnings."""
        warning = generator.get_strategy_warning("scalping")
        assert "scalping" in warning.lower() or "spread" in warning.lower()

    def test_get_strategy_warning_unknown(self, generator):
        """Get strategy warning for unknown type should return generic."""
        warning = generator.get_strategy_warning("nonexistent")
        assert "financial risk" in warning.lower()

    def test_get_jurisdiction_disclaimer(self, generator):
        """Get jurisdiction disclaimer should return known text."""
        text = generator.get_jurisdiction_disclaimer(Jurisdiction.EU)
        assert len(text) > 0

    def test_get_jurisdiction_disclaimer_unknown(self, generator):
        """Unknown jurisdiction should fall back to global."""
        text = generator.get_jurisdiction_disclaimer("unknown")
        assert len(text) > 0


class TestGlobalDisclosureGenerator:
    """Tests for the global risk_disclosure_generator instance."""

    def test_global_instance_exists(self):
        assert risk_disclosure_generator is not None
        assert isinstance(risk_disclosure_generator, RiskDisclosureGenerator)
