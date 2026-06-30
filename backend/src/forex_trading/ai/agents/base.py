"""Base Agent interface for all AI agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class SignalDirection(str, Enum):
    """Trade signal direction."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class MarketRegime(str, Enum):
    """Market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"


@dataclass
class MarketContext:
    """Market context passed to agents for analysis."""
    symbol: str
    timeframe: str
    candles: list[dict] = field(default_factory=list)
    ticks: list[dict] = field(default_factory=list)
    structure: Any = None  # MarketStructure
    session_info: Any = None  # SessionInfo
    regime: MarketRegime = MarketRegime.RANGING
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSignal:
    """Signal produced by an AI agent."""
    agent_id: str
    direction: SignalDirection
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Human-readable explanation
    supporting_data: dict[str, Any] = field(default_factory=dict)
    conflicts_with: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    signal_id: UUID = field(default_factory=uuid4)


class BaseAgent(ABC):
    """
    Base class for all AI agents.

    Each agent specializes in one aspect of market analysis and produces
    a signal with confidence score and reasoning.
    """

    def __init__(self, agent_id: str, name: str) -> None:
        self.agent_id = agent_id
        self.name = name
        self._enabled = True

    @abstractmethod
    async def analyze(self, context: MarketContext) -> AgentSignal:
        """
        Analyze market data and produce a trade signal.

        Args:
            context: Current market context with all available data

        Returns:
            AgentSignal with direction, confidence, and reasoning
        """
        pass

    @abstractmethod
    def get_weight(self, regime: MarketRegime) -> float:
        """
        Get agent weight for current market regime.

        Different agents are more reliable in different market conditions.
        Weight determines influence on final consensus.

        Args:
            regime: Current market regime

        Returns:
            Weight between 0.0 and 1.0
        """
        pass

    @abstractmethod
    def required_data(self) -> list[str]:
        """
        List of data dependencies for this agent.

        Returns:
            List of required data keys (e.g., ["candles", "volume", "ticks"])
        """
        pass

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, name={self.name})"
