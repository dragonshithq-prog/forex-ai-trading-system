"""Session Detector - identifies active global trading sessions."""

from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass


class TradingSession(str, Enum):
    """Global trading sessions."""
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    OFF_SESSION = "off_session"


@dataclass
class SessionInfo:
    """Information about the current trading session."""
    active_session: TradingSession
    sessions_active: list[TradingSession]
    is_overlap: bool
    overlap_sessions: list[TradingSession]
    session_strength: float  # 0.0 - 1.0
    time_to_next_session: timedelta | None


# Session times in UTC
SESSION_TIMES = {
    TradingSession.SYDNEY: {"open": 22, "close": 7},    # 22:00 - 07:00 UTC
    TradingSession.TOKYO: {"open": 0, "close": 9},       # 00:00 - 09:00 UTC
    TradingSession.LONDON: {"open": 7, "close": 16},     # 07:00 - 16:00 UTC
    TradingSession.NEW_YORK: {"open": 12, "close": 21},  # 12:00 - 21:00 UTC
}

# Session liquidity weights
SESSION_WEIGHTS = {
    TradingSession.SYDNEY: 0.3,
    TradingSession.TOKYO: 0.6,
    TradingSession.LONDON: 0.9,
    TradingSession.NEW_YORK: 1.0,
}


class SessionDetector:
    """
    Detect current global trading sessions.

    Identifies:
    - Which sessions are currently active
    - Session overlaps (London/NY = highest liquidity)
    - Session strength based on historical volume
    - Time to next session opening
    """

    def __init__(self, timezone_offset: int = 0) -> None:
        """
        Initialize session detector.

        Args:
            timezone_offset: Hours offset from UTC for display purposes
        """
        self._tz_offset = timezone_offset

    def get_current_session(self, utc_now: datetime | None = None) -> SessionInfo:
        """
        Get current trading session information.

        Args:
            utc_now: Current UTC time (uses now if None)

        Returns:
            SessionInfo with all session details
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)

        current_hour = utc_now.hour
        active_sessions = self._get_active_sessions(current_hour)
        overlaps = self._detect_overlaps(active_sessions)

        # Determine primary session (highest weight)
        primary_session = max(active_sessions, key=lambda s: SESSION_WEIGHTS[s]) if active_sessions else TradingSession.OFF_SESSION

        # Calculate session strength
        strength = sum(SESSION_WEIGHTS[s] for s in active_sessions) / len(active_sessions) if active_sessions else 0.0

        # Time to next session
        time_to_next = self._time_to_next_session(current_hour)

        return SessionInfo(
            active_session=primary_session,
            sessions_active=active_sessions,
            is_overlap=len(overlaps) > 1,
            overlap_sessions=overlaps,
            session_strength=strength,
            time_to_next_session=time_to_next,
        )

    def _get_active_sessions(self, current_hour: int) -> list[TradingSession]:
        """Get all sessions currently active."""
        active = []

        for session, times in SESSION_TIMES.items():
            open_hour = times["open"]
            close_hour = times["close"]

            # Handle overnight sessions (e.g., Sydney: 22-07)
            if open_hour > close_hour:
                if current_hour >= open_hour or current_hour < close_hour:
                    active.append(session)
            else:
                if open_hour <= current_hour < close_hour:
                    active.append(session)

        return active

    def _detect_overlaps(self, active_sessions: list[TradingSession]) -> list[TradingSession]:
        """Detect session overlaps."""
        if len(active_sessions) < 2:
            return active_sessions
        return active_sessions

    def _time_to_next_session(self, current_hour: int) -> timedelta | None:
        """Calculate time until next session opens."""
        next_openings = []

        for session, times in SESSION_TIMES.items():
            open_hour = times["open"]
            if open_hour > current_hour:
                hours_until = open_hour - current_hour
            else:
                hours_until = (24 - current_hour) + open_hour
            next_openings.append(hours_until)

        if not next_openings:
            return None

        min_hours = min(next_openings)
        return timedelta(hours=min_hours)

    def is_high_liquidity_session(self, session_info: SessionInfo) -> bool:
        """Check if current session has high liquidity."""
        return session_info.session_strength >= 0.7 or session_info.is_overlap

    def get_session_pair_affinity(self, session: TradingSession) -> list[str]:
        """Get currency pairs most active during a session."""
        affinity_map = {
            TradingSession.SYDNEY: ["AUDUSD", "NZDUSD", "AUDJPY"],
            TradingSession.TOKYO: ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
            TradingSession.LONDON: ["EURUSD", "GBPUSD", "EURGBP", "USDCHF"],
            TradingSession.NEW_YORK: ["EURUSD", "GBPUSD", "USDCAD", "USDJPY"],
        }
        return affinity_map.get(session, [])
