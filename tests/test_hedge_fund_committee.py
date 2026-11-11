import pytest
import asyncio
from core.agents.hedge_fund_committee import (
    HedgeFundCommittee,
    PersonaVote,
    CommitteeDecision,
)

@pytest.fixture
def sample_market_context():
    return {
        "factors": {
            "zscore": 1.8,
            "ROC5": 0.08,
            "ROC20": 0.15,
            "VOL_MA5_RATIO": 2.2,
            "PRICE_VOLATILITY_20": 0.02,
        },
        "berkshire_data": {
            "market_cap": 1200000000000,
            "daily_volume": 35000000000,
            "staking_yield_pct": 5.0,
            "active_addresses": 950000,
            "annual_network_fees": 800000000,
            "top_holders_share_pct": 0.12,
        },
        "risk_metrics": {
            "var_95_pct": 0.03,  # 3% VaR (safe under 5%)
            "current_drawdown_pct": 0.04,  # 4% drawdown (safe under 15%)
            "liquidation_distance_pct": 0.35,  # 35% safe buffer
            "kelly_fraction": 0.20,
        },
    }

def test_hedge_fund_committee_deliberation_consensus_buy(sample_market_context):
    committee = HedgeFundCommittee()
    decision = asyncio.run(committee.deliberate("BTCUSDT", sample_market_context))

    assert isinstance(decision, CommitteeDecision)
    assert decision.symbol == "BTCUSDT"
    assert decision.risk_veto is False
    assert decision.action == "BUY"
    assert decision.conviction_score > 0.6
    assert 0.0 < decision.suggested_sizing_pct <= 0.25
    assert len(decision.persona_votes) >= 4
    # Check personas
    persona_names = [v.persona for v in decision.persona_votes]
    assert "Jim Simons" in persona_names
    assert "Cathie Wood" in persona_names
    assert "Warren Buffett & Li Lu" in persona_names
    assert "Risk Officer" in persona_names
    # Synthesis memo should mention consensus
    assert "Consensus Verdict: BUY" in decision.synthesis_memo

def test_hedge_fund_committee_risk_officer_veto(sample_market_context):
    committee = HedgeFundCommittee(max_var_limit=0.05)
    # Inject dangerous risk: VaR is 8% (> 5% limit) and drawdown is 20% (> 15% limit)
    sample_market_context["risk_metrics"]["var_95_pct"] = 0.08
    sample_market_context["risk_metrics"]["current_drawdown_pct"] = 0.20

    decision = asyncio.run(committee.deliberate("BTCUSDT", sample_market_context))

    assert decision.risk_veto is True
    assert decision.action == "HOLD"
    assert decision.suggested_sizing_pct == 0.0
    assert decision.conviction_score == 0.0
    assert decision.risk_veto_reason is not None
    assert "VaR" in decision.risk_veto_reason or "drawdown" in decision.risk_veto_reason
    assert "VETO" in decision.synthesis_memo

def test_hedge_fund_committee_caching(sample_market_context):
    committee = HedgeFundCommittee(cache_ttl_seconds=60)
    decision1 = asyncio.run(committee.deliberate("BTCUSDT", sample_market_context))
    decision2 = asyncio.run(committee.deliberate("BTCUSDT", sample_market_context))
    # Timestamp or object identity verifies cached response
    assert decision1.timestamp == decision2.timestamp
    assert decision1.synthesis_memo == decision2.synthesis_memo

def test_hedge_fund_committee_sync_wrapper(sample_market_context):
    committee = HedgeFundCommittee()
    decision = committee.deliberate_sync("BTCUSDT", sample_market_context)
    assert isinstance(decision, CommitteeDecision)
    assert decision.symbol == "BTCUSDT"
    assert decision.action == "BUY"

def test_hedge_fund_committee_missing_data():
    committee = HedgeFundCommittee()
    decision = committee.deliberate_sync("UNKNOWN", {})
    assert decision.symbol == "UNKNOWN"
    assert decision.action == "HOLD"
    assert decision.suggested_sizing_pct == 0.0
