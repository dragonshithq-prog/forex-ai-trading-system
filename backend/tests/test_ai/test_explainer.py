"""Tests for TradeExplainer — TradeExplanation generation."""

from __future__ import annotations

import pytest

from forex_trading.ai.agents.base import AgentSignal, MarketContext, MarketRegime, SignalDirection
from forex_trading.ai.consensus.engine import ConsensusResult, ConsensusEngine
from forex_trading.ai.xai.explainer import TradeExplainer, TradeExplanation


class TestTradeExplainer:
    """Tests for the TradeExplainer."""

    def setup_method(self):
        self.explainer = TradeExplainer()
        self.engine = ConsensusEngine(min_agents=3, agreement_threshold=0.60)

    def _signal(self, agent_id: str, direction: SignalDirection, confidence: float, reasoning: str = "") -> AgentSignal:
        return AgentSignal(
            agent_id=agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning or f"{agent_id} analysis",
        )

    def test_explain_decision_returns_trade_explanation(self):
        """explain_decision should return a complete TradeExplanation."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.75,
            agreement_ratio=0.80,
            conflict_ratio=0.10,
            supporting_agents=["trend_ai", "momentum"],
            conflicting_agents=["liquidity"],
            is_actionable=True,
            reasoning="Strong uptrend confirmed by multiple agents",
            agent_breakdown={
                "trend_ai": self._signal("trend_ai", SignalDirection.LONG, 0.8, "Strong uptrend"),
                "momentum": self._signal("momentum", SignalDirection.LONG, 0.7, "Positive momentum"),
                "liquidity": self._signal("liquidity", SignalDirection.SHORT, 0.3, "Liquidity low"),
            },
        )
        context = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            regime=MarketRegime.TRENDING_UP,
            metadata={"spread": 1.2, "entry_price": 1.1000},
        )
        risk_assessment = {
            "spread": 1.2,
            "current_drawdown_pct": 0.5,
            "risk_vetoed": False,
        }

        explanation = self.explainer.explain_decision(consensus, context, risk_assessment)
        assert isinstance(explanation, TradeExplanation)
        assert explanation.direction == "LONG"
        assert explanation.confidence_score == 0.75
        assert explanation.market_regime == "trending_up"
        assert explanation.strategy_selected is not None
        assert len(explanation.supporting_signals) == 2
        assert len(explanation.conflicting_signals) == 1

    def test_explain_decision_neutral(self):
        """Neutral consensus should still produce an explanation."""
        consensus = ConsensusResult(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            agreement_ratio=0.0,
            conflict_ratio=1.0,
            supporting_agents=[],
            conflicting_agents=["trend_ai", "momentum"],
            is_actionable=False,
            reasoning="Insufficient signal",
            agent_breakdown={
                "trend_ai": self._signal("trend_ai", SignalDirection.LONG, 0.3),
                "momentum": self._signal("momentum", SignalDirection.SHORT, 0.3),
            },
        )
        context = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            regime=MarketRegime.RANGING,
        )

        explanation = self.explainer.explain_decision(consensus, context, {"error": "No clear signal"})
        assert explanation.direction == "NEUTRAL"
        assert explanation.confidence_score == 0.0

    def test_strategy_selection_based_on_top_agents(self):
        """Strategy should be inferred from the top supporting agents."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.8,
            agreement_ratio=0.9,
            conflict_ratio=0.1,
            supporting_agents=["smart_money", "market_structure", "trend"],
            conflicting_agents=[],
            is_actionable=True,
            reasoning="Smart money + structure confluence",
            agent_breakdown={
                "smart_money": self._signal("smart_money", SignalDirection.LONG, 0.9),
                "market_structure": self._signal("market_structure", SignalDirection.LONG, 0.8),
            },
        )
        context = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            regime=MarketRegime.TRENDING_UP,
        )

        strategy = self.explainer._select_strategy(consensus, context)
        assert "Smart Money Concepts" in strategy

    def test_entry_rationale_builds_from_supporting_agents(self):
        """Entry rationale should reference top supporting agents."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.75,
            agreement_ratio=0.8,
            conflict_ratio=0.1,
            supporting_agents=["trend_ai"],
            conflicting_agents=[],
            is_actionable=True,
            reasoning="Trend following confirmed",
            agent_breakdown={
                "trend_ai": self._signal("trend_ai", SignalDirection.LONG, 0.75, "Price above EMA 50"),
            },
        )
        context = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            regime=MarketRegime.TRENDING_UP,
        )

        rationale = self.explainer._build_entry_rationale(consensus, context)
        assert "EURUSD" in rationale
        assert "LONG" in rationale
        assert "trend_ai" in rationale

    def test_exit_rationale_from_exit_agent(self):
        """Exit rationale should use the exit_ai signal if available."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.75,
            agreement_ratio=0.8,
            conflict_ratio=0.1,
            supporting_agents=["exit_ai"],
            conflicting_agents=[],
            is_actionable=True,
            reasoning="",
            agent_breakdown={
                "exit_ai": self._signal("exit_ai", SignalDirection.LONG, 0.7, "Exit at resistance 1.1150"),
            },
        )
        context = MarketContext(symbol="EURUSD", timeframe="H1")

        rationale = self.explainer._build_exit_rationale(consensus, context)
        assert "Exit at resistance" in rationale

    def test_exit_rationale_fallback_long(self):
        """Long exit fallback should describe generic exit plan."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.75,
            agreement_ratio=0.8,
            conflict_ratio=0.1,
            supporting_agents=["trend_ai"],
            conflicting_agents=[],
            is_actionable=True,
            reasoning="",
            agent_breakdown={"trend_ai": self._signal("trend_ai", SignalDirection.LONG, 0.75)},
        )
        context = MarketContext(symbol="EURUSD", timeframe="H1")

        rationale = self.explainer._build_exit_rationale(consensus, context)
        assert "trail stop" in rationale.lower()

    def test_session_description(self):
        """Session description should include symbol and timeframe."""
        context = MarketContext(symbol="EURUSD", timeframe="H1")
        desc = self.explainer._describe_session(context)
        assert "EURUSD" in desc
        assert "H1" in desc

    def test_supporting_signals_sorted_by_confidence(self):
        """Supporting signals should be sorted by confidence descending."""
        consensus = ConsensusResult(
            direction=SignalDirection.LONG,
            confidence=0.7,
            agreement_ratio=0.8,
            conflict_ratio=0.1,
            supporting_agents=["a", "b"],
            conflicting_agents=[],
            is_actionable=True,
            reasoning="",
            agent_breakdown={
                "a": self._signal("a", SignalDirection.LONG, 0.9),
                "b": self._signal("b", SignalDirection.LONG, 0.5),
            },
        )
        context = MarketContext(symbol="EURUSD", timeframe="H1")

        explanation = self.explainer.explain_decision(consensus, context, {})
        assert explanation.supporting_signals[0]["confidence"] >= explanation.supporting_signals[1]["confidence"]
