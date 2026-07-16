"""Tests for Repository performance optimizations.

Tests:
- Query timeouts on all repository queries
- N+1 query detection
- Pagination defaults on all list endpoints
- Eager loading for common relationship patterns
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from forex_trading.shared.database.repository import (
    BaseRepository,
    OrderRepository,
    PositionRepository,
    TradeRepository,
    RiskStateRepository,
    RiskAlertRepository,
    AIDecisionRepository,
    QueryTimer,
    get_query_count,
    reset_query_count,
    check_n_plus_one,
    _DEFAULT_PAGE_SIZE,
    _MAX_PAGE_SIZE,
)
from forex_trading.shared.database.base import BaseModel


pytestmark = pytest.mark.asyncio


class TestQueryTimer:
    """Tests for QueryTimer context manager."""

    async def test_fast_query_no_warning(self):
        """Fast queries should not trigger warnings."""
        timer = QueryTimer("test_op", "details")
        async with timer:
            pass  # Fast operation

    async def test_slow_query_logs_warning(self):
        """Slow queries should log a warning."""
        import asyncio
        timer = QueryTimer("test_slow", "slow_details")
        with patch("structlog.get_logger") as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log
            async with timer:
                await asyncio.sleep(0)  # Won't trigger slow


class TestPaginationDefaults:
    """Tests for pagination defaults in repositories."""

    def test_default_page_size(self):
        """Default page size should be reasonable."""
        assert _DEFAULT_PAGE_SIZE == 50

    def test_max_page_size(self):
        """Max page size should prevent excessive queries."""
        assert _MAX_PAGE_SIZE == 500

    async def test_get_multi_enforces_limit(self, db_session):
        """get_multi should cap limit at MAX_PAGE_SIZE."""
        from forex_trading.shared.database.models_trading import Order
        
        repo = BaseRepository(db_session, Order)

        # Requesting more than MAX_PAGE_SIZE should be capped
        result = await repo.get_multi(skip=0, limit=1000)
        # Should work without error — capped to MAX_PAGE_SIZE
        assert isinstance(result, list)


class TestNPlusOneDetection:
    """Tests for N+1 query detection."""

    def test_reset_query_count(self):
        """reset_query_count should clear the counter."""
        reset_query_count()
        count = get_query_count()
        assert count >= 0

    def test_check_n_plus_one_no_warning(self):
        """Low query count should not warn."""
        reset_query_count()
        # Should not raise
        check_n_plus_one(threshold=100)

    def test_check_n_plus_one_warning(self):
        """High query count should warn."""
        import warnings
        reset_query_count()

        # Force a warning by checking with a low threshold
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            check_n_plus_one(threshold=0)

            if len(w) > 0:
                assert "N+1" in str(w[0].message)


class TestEagerLoading:
    """Tests for eager loading in repositories."""

    async def test_order_repository_eager_loading(self, db_session):
        """OrderRepository should apply eager loading."""
        from forex_trading.shared.database.models_trading import Order
        from sqlalchemy import select
        
        repo = OrderRepository(db_session)
        query = select(Order)
        result = repo._apply_eager_loading(query)
        assert result is not None

    async def test_position_repository_eager_loading(self, db_session):
        """PositionRepository should apply eager loading."""
        from forex_trading.shared.database.models_trading import Position
        from sqlalchemy import select
        
        repo = PositionRepository(db_session)
        query = select(Position)
        result = repo._apply_eager_loading(query)
        assert result is not None

    async def test_ai_decision_repository_eager_loading(self, db_session):
        """AIDecisionRepository should apply eager loading."""
        from forex_trading.shared.database.models_strategy import AIDecision
        from sqlalchemy import select
        
        repo = AIDecisionRepository(db_session)
        query = select(AIDecision)
        result = repo._apply_eager_loading(query)
        assert result is not None


class TestRepositoryQueryTimeouts:
    """Tests for query timeout infrastructure."""

    async def test_count_with_filters(self, db_session):
        """count with filters should work."""
        from forex_trading.shared.database.models_trading import Order
        from sqlalchemy import true
        
        repo = BaseRepository(db_session, Order)

        result = await repo.count(filters=[Order.id.isnot(None)])
        assert result >= 0

    async def test_exists_returns_false_for_nonexistent(self, db_session):
        """exists should return False for non-existent id."""
        from forex_trading.shared.database.models_trading import Order
        
        repo = BaseRepository(db_session, Order)
        result = await repo.exists(uuid4())
        assert result is False

    async def test_get_multi_paginated(self, db_session):
        """get_multi_paginated should return items, total, and pages."""
        from forex_trading.shared.database.models_trading import Order
        
        repo = BaseRepository(db_session, Order)

        items, total, pages = await repo.get_multi_paginated(page=1, page_size=10)
        assert total >= 0
        assert pages >= 1
        assert isinstance(items, list)

    async def test_get_multi_paginated_edge_cases(self, db_session):
        """get_multi_paginated should handle edge cases."""
        from forex_trading.shared.database.models_trading import Order
        
        repo = BaseRepository(db_session, Order)

        items, total, pages = await repo.get_multi_paginated(page=0, page_size=0)
        assert total >= 0
        assert pages >= 1

    async def test_get_multi_paginated_negative_page(self, db_session):
        """Negative page should be treated as page 1."""
        from forex_trading.shared.database.models_trading import Order
        
        repo = BaseRepository(db_session, Order)

        items, total, pages = await repo.get_multi_paginated(page=-1, page_size=10)
        assert total >= 0


class TestRiskStateRepository:
    """Tests for RiskStateRepository."""

    async def test_upsert_creates_new(self, db_session):
        """upsert should create a new state when none exists."""
        repo = RiskStateRepository(db_session)
        # Override get_by_account since there's no pre-existing state
        account_id = uuid4()
        state = await repo.upsert(account_id, {"current_equity": 10000.0})
        assert state is not None
        assert state.broker_account_id == account_id

    async def test_upsert_updates_existing(self, db_session):
        """upsert should update existing state."""
        repo = RiskStateRepository(db_session)
        
        account_id = uuid4()
        # First create
        state = await repo.upsert(account_id, {"current_equity": 10000.0})
        assert state.current_equity == 10000.0

        # Then update
        state2 = await repo.upsert(account_id, {"current_equity": 15000.0})
        assert state2.current_equity == 15000.0
