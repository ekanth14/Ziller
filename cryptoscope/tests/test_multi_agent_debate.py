"""Tests for adversarial multi-agent deliberation and consensus engine."""
import pytest
from cryptoscope.agents.researchers.bull_researcher import BullResearcher
from cryptoscope.agents.researchers.bear_researcher import BearResearcher
from cryptoscope.agents.risk.tri_debate import run_tri_risk_debate
from cryptoscope.agents.consensus import DeliberationConsensusEngine


class TestMultiAgentDeliberation:
    def test_bull_researcher_generates_thesis(self):
        bull = BullResearcher()
        indicators = {
            "close": 60000.0,
            "ema20": 59500.0,
            "ema50": 58000.0,
            "rsi14": 56.0,
            "order_blocks": [{"type": "BULLISH_OB", "low": 59000.0, "high": 59400.0}],
        }
        res = bull.formulate_thesis("BTCUSDT", indicators)
        assert res["role"] == "bull_researcher"
        assert "BTCUSDT" in res["thesis"]
        assert len(res["evidence"]) >= 2
        assert res["conviction"] > 0.6

    def test_bear_researcher_generates_counter_thesis(self):
        bear = BearResearcher()
        indicators = {
            "close": 60000.0,
            "ema20": 59500.0,
            "ema50": 61000.0,
            "rsi14": 74.0,  # Overbought
            "order_blocks": [{"type": "BEARISH_OB", "low": 60500.0, "high": 61200.0}],
        }
        res = bear.formulate_thesis("BTCUSDT", indicators, opponent_argument="Bull sees breakout")
        assert res["role"] == "bear_researcher"
        assert "BTCUSDT" in res["thesis"]
        assert len(res["evidence"]) >= 2
        assert len(res["counterarguments"]) >= 1

    def test_tri_risk_debate_governance(self):
        setup = {
            "symbol": "ETHUSDT",
            "entry_price": 3000.0,
            "stop_loss": 2940.0,  # 2% stop
            "take_profit": 3120.0, # 4% target (2R)
            "risk_reward_ratio": 2.0,
        }
        res = run_tri_risk_debate(setup, balance=10000.0)
        assert "conservative" in res
        assert "aggressive" in res
        assert "neutral_consensus" in res
        assert res["approved_risk_pct"] == 2.0
        assert res["max_position_size"] > 0

    def test_deliberation_consensus_engine(self):
        engine = DeliberationConsensusEngine()
        indicators = {
            "close": 60000.0,
            "ema20": 59500.0,
            "ema50": 58000.0,
            "rsi14": 58.0,
            "directional_score": 45.0,
            "atr14": 800.0,
            "order_blocks": [{"type": "BULLISH_OB", "low": 59000.0, "high": 59400.0}],
        }
        decision = engine.deliberate("BTCUSDT", indicators, balance=10000.0)
        assert decision["symbol"] == "BTCUSDT"
        assert decision["action"] in ["BUY", "SELL", "STAND_ASIDE"]
        assert -100.0 <= decision["conviction_score"] <= 100.0
        assert "bull_thesis" in decision
        assert "bear_thesis" in decision
        assert "risk_debate" in decision
        assert "simulation_odds" in decision
