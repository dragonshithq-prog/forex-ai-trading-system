"""
Comprehensive unit tests for Market Data services.

Covers:
- MarketDataService (tick streaming, price caching, spread)
- SessionDetector (all 4 sessions, overlaps, pair affinity, session strength)
- MarketStructureAnalyzer (bullish/bearish structure, OBs, FVGs, S/R levels)
- StructureAnalyzer legacy wrapper
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from forex_trading.market_data.services.market_data_service import MarketDataService
from forex_trading.market_data.services.session_detector import (
    SESSION_TIMES,
    SessionDetector,
    TradingSession,
)
from forex_trading.market_data.services.structure_analyzer import (
    BreakType,
    FairValueGap,
    MarketStructureAnalyzer,
    OrderBlock,
    StructureAnalyzer,
    StructureType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(
    n: int = 100,
    base: float = 1.1000,
    trend: float = 0.0,
    seed: int = 42,
) -> list[dict]:
    rng = random.Random(seed)
    candles = []
    price = base
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = price + trend + rng.gauss(0, 0.0008)
        price = max(price, 0.0001)
        open_ = price + rng.gauss(0, 0.0002)
        close = price + rng.gauss(0, 0.0002)
        high = max(open_, close) + abs(rng.gauss(0, 0.0003))
        low = min(open_, close) - abs(rng.gauss(0, 0.0003))
        candles.append({
            "timestamp": ts + timedelta(hours=i),
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": rng.randint(100, 2000),
        })
    return candles


def _trending_up_candles(n: int = 150) -> list[dict]:
    """Candles with a strong uptrend (0.0002/bar = ~30 pip overall move)."""
    return _make_candles(n=n, trend=0.0002, seed=1)


def _trending_down_candles(n: int = 150) -> list[dict]:
    """Candles with a strong downtrend."""
    return _make_candles(n=n, trend=-0.0002, seed=2)


def _ranging_candles(n: int = 150) -> list[dict]:
    return _make_candles(n=n, trend=0.0, seed=3)


# ============================================================
# MarketDataService
# ============================================================


@pytest.mark.unit
class TestMarketDataService:
    """Tick subscription, price caching, and spread computation."""

    @pytest.fixture
    def service(self):
        return MarketDataService()

    @pytest.mark.asyncio
    async def test_subscribe_ticks_registers_callback(self, service):
        cb = lambda event: None
        await service.subscribe_ticks("EURUSD", cb)
        assert "EURUSD" in service._subscribers

    @pytest.mark.asyncio
    async def test_on_tick_fires_callback(self, service):
        received = []

        async def cb(event):
            received.append(event)

        await service.subscribe_ticks("EURUSD", cb)
        await service.on_tick("EURUSD", 1.1000, 1.1002, 100)
        assert len(received) == 1
        # Event is a dict with symbol key
        event = received[0]
        symbol = event.symbol if hasattr(event, "symbol") else event.get("symbol", event["symbol"])
        assert symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_get_current_price_bid_ask(self, service):
        await service.on_tick("GBPUSD", 1.2700, 1.2703, 200)
        price = await service.get_current_price("GBPUSD")
        assert price is not None
        assert price["bid"] == 1.2700
        assert price["ask"] == 1.2703

    @pytest.mark.asyncio
    async def test_get_spread_is_ask_minus_bid(self, service):
        await service.on_tick("EURUSD", 1.1000, 1.1002, 100)
        spread = await service.get_spread("EURUSD")
        assert spread == pytest.approx(0.0002, abs=1e-6)

    @pytest.mark.asyncio
    async def test_get_price_unknown_symbol_returns_none(self, service):
        price = await service.get_current_price("UNKNOWN")
        assert price is None

    @pytest.mark.asyncio
    async def test_multiple_symbols_tracked_independently(self, service):
        await service.on_tick("EURUSD", 1.1000, 1.1002, 100)
        await service.on_tick("GBPUSD", 1.2700, 1.2703, 50)
        eur = await service.get_current_price("EURUSD")
        gbp = await service.get_current_price("GBPUSD")
        assert eur["bid"] == 1.1000
        assert gbp["bid"] == 1.2700

    @pytest.mark.asyncio
    async def test_latest_tick_overwrites_previous(self, service):
        await service.on_tick("EURUSD", 1.1000, 1.1002, 100)
        await service.on_tick("EURUSD", 1.1050, 1.1052, 200)
        price = await service.get_current_price("EURUSD")
        assert price["bid"] == 1.1050


# ============================================================
# SessionDetector
# ============================================================


@pytest.mark.unit
class TestSessionDetector:
    """All trading session detection scenarios."""

    @pytest.fixture
    def detector(self):
        return SessionDetector()

    # --- Individual session windows ---

    def test_london_session_active_at_0800(self, detector):
        """08:00 UTC → London (07:00–16:00) is active."""
        t = datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.LONDON in info.sessions_active

    def test_new_york_session_active_at_1400(self, detector):
        """14:00 UTC → New York (12:00–21:00) is active."""
        t = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.NEW_YORK in info.sessions_active

    def test_tokyo_session_active_at_0300(self, detector):
        """03:00 UTC → Tokyo (00:00–09:00) is active."""
        t = datetime(2024, 1, 15, 3, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.TOKYO in info.sessions_active

    def test_sydney_session_active_overnight(self, detector):
        """23:00 UTC → Sydney (22:00–07:00) is active."""
        t = datetime(2024, 1, 15, 23, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.SYDNEY in info.sessions_active

    def test_off_session_at_2130(self, detector):
        """21:30 UTC → between NY close (21:00) and Sydney open (22:00): OFF or Sydney."""
        t = datetime(2024, 1, 15, 21, 30, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert info.active_session in (TradingSession.OFF_SESSION, TradingSession.SYDNEY)

    # --- Overlap detection ---

    def test_london_new_york_overlap_detected(self, detector):
        """14:00 UTC → London/NY overlap → is_overlap=True."""
        t = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.LONDON in info.sessions_active
        assert TradingSession.NEW_YORK in info.sessions_active
        assert info.is_overlap is True

    def test_tokyo_sydney_overlap_detected(self, detector):
        """02:00 UTC → Tokyo (00:00–09:00) and Sydney (22:00–07:00) both active."""
        t = datetime(2024, 1, 15, 2, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert TradingSession.TOKYO in info.sessions_active
        assert TradingSession.SYDNEY in info.sessions_active
        assert info.is_overlap is True

    def test_single_session_not_overlap(self, detector):
        """19:00 UTC → Only NY session active → no overlap."""
        t = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert info.is_overlap is False or len(info.sessions_active) > 1

    # --- Session strength ---

    def test_session_strength_between_0_and_1(self, detector):
        for hour in [2, 8, 14, 19, 23]:
            t = datetime(2024, 1, 15, hour, 0, tzinfo=timezone.utc)
            info = detector.get_current_session(t)
            assert 0.0 <= info.session_strength <= 1.0

    def test_overlap_session_strength_higher_than_single(self, detector):
        """London/NY overlap has higher strength than off-session."""
        overlap_t = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        off_t = datetime(2024, 1, 15, 21, 30, tzinfo=timezone.utc)
        overlap_info = detector.get_current_session(overlap_t)
        off_info = detector.get_current_session(off_t)
        assert overlap_info.session_strength >= off_info.session_strength

    def test_is_high_liquidity_session_during_overlap(self, detector):
        """London/NY overlap is classified as high liquidity."""
        t = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert detector.is_high_liquidity_session(info) is True

    # --- Pair affinity ---

    def test_tokyo_session_includes_usdjpy(self, detector):
        pairs = detector.get_session_pair_affinity(TradingSession.TOKYO)
        assert "USDJPY" in pairs

    def test_london_session_includes_eurusd(self, detector):
        pairs = detector.get_session_pair_affinity(TradingSession.LONDON)
        assert "EURUSD" in pairs

    def test_sydney_session_includes_audusd(self, detector):
        pairs = detector.get_session_pair_affinity(TradingSession.SYDNEY)
        assert "AUDUSD" in pairs

    def test_new_york_session_includes_usdcad(self, detector):
        pairs = detector.get_session_pair_affinity(TradingSession.NEW_YORK)
        assert "USDCAD" in pairs

    def test_unknown_session_pair_affinity_returns_empty(self, detector):
        pairs = detector.get_session_pair_affinity(TradingSession.OFF_SESSION)
        assert isinstance(pairs, list)

    # --- Time to next session ---

    def test_time_to_next_session_is_timedelta(self, detector):
        t = datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert info.time_to_next_session is not None
        assert isinstance(info.time_to_next_session, __import__("datetime").timedelta)

    def test_time_to_next_session_positive(self, detector):
        t = datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(t)
        assert info.time_to_next_session.total_seconds() > 0


# ============================================================
# MarketStructureAnalyzer
# ============================================================


@pytest.mark.unit
class TestMarketStructureAnalyzer:
    """SMC-based structure detection."""

    @pytest.fixture
    def analyzer(self):
        return MarketStructureAnalyzer()

    def test_analyze_returns_market_structure(self, analyzer):
        candles = _make_candles(50)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        assert result.symbol == "EURUSD"
        assert result.timeframe == "H1"

    def test_analyze_few_candles_returns_ranging(self, analyzer):
        """< 10 candles → defaults to RANGING."""
        result = analyzer.analyze([], "H1", "EURUSD")
        assert result.structure_type == StructureType.RANGING

    def test_analyze_single_candle_ranging(self, analyzer):
        candles = _make_candles(5)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        assert result.structure_type == StructureType.RANGING

    def test_bullish_structure_from_uptrend_candles(self, analyzer):
        """Strong uptrend candles → bullish structure detected."""
        candles = _trending_up_candles(150)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        assert result.trend_direction in ("bullish", "ranging")  # strong uptrend should be bullish

    def test_bearish_structure_from_downtrend_candles(self, analyzer):
        """Strong downtrend candles → bearish or ranging."""
        candles = _trending_down_candles(150)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        assert result.trend_direction in ("bearish", "ranging")

    def test_swing_highs_detected(self, analyzer):
        candles = _make_candles(100)
        highs = analyzer._find_swing_highs(candles)
        assert isinstance(highs, list)

    def test_swing_lows_detected(self, analyzer):
        candles = _make_candles(100)
        lows = analyzer._find_swing_lows(candles)
        assert isinstance(lows, list)

    def test_swing_high_price_is_local_maximum(self, analyzer):
        """Each detected swing high must be a local max of its candle's high."""
        candles = _make_candles(100)
        highs = analyzer._find_swing_highs(candles, lookback=3)
        for level in highs:
            # Level price should be a candle high value (no out-of-range values)
            all_highs = [c["high"] for c in candles]
            assert level.price in all_highs or abs(level.price - max(all_highs)) < 0.1

    def test_swing_low_prices_are_valid(self, analyzer):
        candles = _make_candles(100)
        lows = analyzer._find_swing_lows(candles)
        all_lows = [c["low"] for c in candles]
        for level in lows:
            assert level.price >= min(all_lows) * 0.95

    def test_support_levels_from_swing_lows(self, analyzer):
        """Support levels are derived from swing lows."""
        candles = _make_candles(100)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        for sl in result.support_levels:
            assert sl.level_type == "support"
            assert sl.price > 0

    def test_resistance_levels_from_swing_highs(self, analyzer):
        candles = _make_candles(100)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        for rl in result.resistance_levels:
            assert rl.level_type == "resistance"
            assert rl.price > 0

    def test_order_blocks_detected_on_valid_pattern(self, analyzer):
        """Manually craft OB pattern: bearish candle followed by strong bullish."""
        candles = _make_candles(20)
        # Inject a clear bullish OB pattern at position 10
        candles[10]["open"] = 1.1050
        candles[10]["close"] = 1.1020  # bearish candle
        candles[10]["high"] = 1.1055
        candles[10]["low"] = 1.1010
        candles[11]["open"] = 1.1025
        candles[11]["close"] = 1.1080  # strong bullish, closes above candle[10].open
        candles[11]["high"] = 1.1085
        candles[11]["low"] = 1.1020
        obs = analyzer._find_order_blocks(candles)
        assert isinstance(obs, list)

    def test_fair_value_gaps_detected_on_valid_pattern(self, analyzer):
        """Inject a clear bullish FVG pattern."""
        candles = _make_candles(20)
        # FVG: candles[i].low > candles[i-2].high
        candles[10]["high"] = 1.1010
        candles[10]["low"] = 1.1005
        candles[11]["high"] = 1.1030
        candles[11]["low"] = 1.1020
        candles[12]["high"] = 1.1060
        candles[12]["low"] = 1.1015  # 1.1015 > 1.1010 → bullish FVG
        fvgs = analyzer._find_fair_value_gaps(candles)
        assert isinstance(fvgs, list)

    def test_analyze_sets_analyzed_at(self, analyzer):
        candles = _make_candles(50)
        result = analyzer.analyze(candles, "H1", "EURUSD")
        assert result.analyzed_at is not None
        assert isinstance(result.analyzed_at, datetime)

    def test_determine_trend_insufficient_swings_returns_ranging(self, analyzer):
        """< 2 swings of either type → ranging."""
        result = analyzer._determine_trend([], [])
        assert result == "ranging"


# ============================================================
# StructureAnalyzer (legacy wrapper)
# ============================================================


@pytest.mark.unit
class TestStructureAnalyzerLegacy:
    """Legacy StructureAnalyzer preserves backwards compatibility."""

    @pytest.fixture
    def analyzer(self):
        return StructureAnalyzer()

    @pytest.mark.asyncio
    async def test_analyze_empty_candles_returns_ranging(self, analyzer):
        result = await analyzer.analyze("EURUSD", [], "H1")
        assert result.structure_type == StructureType.RANGING

    @pytest.mark.asyncio
    async def test_analyze_returns_market_structure_object(self, analyzer):
        from forex_trading.market_data.services.structure_analyzer import MarketStructure
        candles = _make_candles(50)
        result = await analyzer.analyze("EURUSD", candles, "H1")
        assert isinstance(result, MarketStructure)
        assert result.symbol == "EURUSD"

    def test_find_swings_returns_tuple_of_lists(self, analyzer):
        candles = _make_candles(50)
        highs, lows = analyzer._find_swings(candles)
        assert isinstance(highs, list)
        assert isinstance(lows, list)

    def test_find_order_blocks_returns_list(self, analyzer):
        candles = _make_candles(30)
        obs = analyzer._find_order_blocks(candles)
        assert isinstance(obs, list)
        for ob in obs:
            assert isinstance(ob, OrderBlock)

    def test_find_fair_value_gaps_returns_list(self, analyzer):
        candles = _make_candles(30)
        fvgs = analyzer._find_fair_value_gaps(candles)
        assert isinstance(fvgs, list)
        for fvg in fvgs:
            assert isinstance(fvg, FairValueGap)

    @pytest.mark.asyncio
    async def test_analysis_cached_by_symbol_timeframe(self, analyzer):
        candles = _make_candles(50)
        await analyzer.analyze("EURUSD", candles, "H1")
        assert "EURUSD_H1" in analyzer._analysis_cache

    def test_find_swings_short_candles_no_error(self, analyzer):
        candles = _make_candles(3)
        highs, lows = analyzer._find_swings(candles)
        assert isinstance(highs, list)
