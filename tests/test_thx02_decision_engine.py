import pytest
import math
from core.agents.thx02_decision_engine import (
    THX02DecisionEngine,
    THX02TradeDecision,
    ExecutionMode,
)
from core.agents.hedge_fund_committee import HedgeFundCommittee


def test_ask_choice_basic():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    state = {
        "zscore": 2.1,
        "ROC20": 0.12,
        "cvd": 5000.0,
        "volatility": 0.02,
    }
    question = "What is the optimal directional trading posture?"
    choices = ["BUY", "SELL", "HOLD"]
    res = engine.ask_choice(state, question, choices)

    assert "best_choice" in res
    assert res["best_choice"] in choices
    assert res["best_choice"] == "BUY"  # High zscore + ROC20 + positive CVD
    assert "probabilities" in res
    assert set(res["probabilities"].keys()) == set(choices)
    # Probabilities must sum to 1.0
    assert sum(res["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)
    assert res["probabilities"]["BUY"] > res["probabilities"]["SELL"]
    assert "thought" in res
    assert "<think>" in res["thought"]


def test_ask_choice_empty_choices_raises():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    with pytest.raises(ValueError, match="choices must not be empty"):
        engine.ask_choice({}, "Question?", [])


def test_ask_noul_boolean_query():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    # High risk state
    state = {
        "var_95": 0.08,
        "drawdown": 0.18,
        "volatility": 0.09,
    }
    question = "Are market risk parameters safe for high leverage entry?"
    res = engine.ask_noul(state, question)

    assert isinstance(res["result"], bool)
    assert res["result"] is False  # High risk -> No
    assert "confidence" in res
    assert 0.5 <= res["confidence"] <= 1.0
    assert "prob_yes" in res
    assert "prob_no" in res
    assert res["prob_yes"] + res["prob_no"] == pytest.approx(1.0, abs=1e-5)
    assert res["prob_no"] > res["prob_yes"]
    assert "<think>" in res["thought"]


def test_ask_score_distribution():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    state = {
        "zscore": 1.5,
        "ROC5": 0.04,
        "active_addresses": 900000,
    }
    question = "Rate fundamental network and momentum health on a scale of 1 to 10"
    res = engine.ask_score(state, question, min_val=1, max_val=10)

    assert "score" in res
    assert 1.0 <= res["score"] <= 10.0
    assert "distribution" in res
    dist = res["distribution"]
    assert len(dist) == 10
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-5)
    assert "<think>" in res["thought"]


def test_ask_score_invalid_range_raises():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    with pytest.raises(ValueError, match="min_val must be strictly less than max_val"):
        engine.ask_score({}, "Rate this", min_val=10, max_val=5)


def test_deliberate_regime_and_trade_bullish():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    state = {
        "symbol": "BTCUSDT",
        "price": 68000.0,
        "factors": {
            "zscore": 2.2,
            "ROC5": 0.05,
            "ROC20": 0.14,
            "VOL_MA5_RATIO": 2.0,
            "PRICE_VOLATILITY_20": 0.02,
        },
        "order_flow": {
            "cvd": 12500.0,
            "delta": 3200.0,
        },
        "risk_metrics": {
            "var_95_pct": 0.02,
            "current_drawdown_pct": 0.03,
            "liquidation_distance_pct": 0.40,
            "kelly_fraction": 0.18,
        },
    }
    decision = engine.deliberate_regime_and_trade(state)

    assert isinstance(decision, THX02TradeDecision)
    assert decision.action == "BUY"
    assert decision.regime in ("TRENDING_BULLISH", "LOW_VOL_CONSOLIDATION")
    assert decision.conviction > 0.60
    assert decision.risk_cleared is True
    assert 0.0 < decision.suggested_sizing_pct <= 0.25
    assert "<think>" in decision.thought
    assert "probabilities" in decision.__dict__ or hasattr(decision, "probabilities")
    assert decision.probabilities["BUY"] > decision.probabilities["SELL"]


def test_deliberate_regime_and_trade_bearish():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    state = {
        "symbol": "BTCUSDT",
        "factors": {
            "zscore": -2.4,
            "ROC5": -0.07,
            "ROC20": -0.15,
            "VOL_MA5_RATIO": 2.5,
            "PRICE_VOLATILITY_20": 0.05,
        },
        "order_flow": {
            "cvd": -15000.0,
            "delta": -4000.0,
        },
        "risk_metrics": {
            "var_95_pct": 0.03,
            "current_drawdown_pct": 0.05,
            "liquidation_distance_pct": 0.30,
            "kelly_fraction": 0.10,
        },
    }
    decision = engine.deliberate_regime_and_trade(state)

    assert decision.action == "SELL"
    assert decision.regime == "TRENDING_BEARISH"
    assert decision.conviction > 0.60
    assert decision.probabilities["SELL"] > decision.probabilities["BUY"]


def test_deliberate_regime_and_trade_high_vol_chop():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    state = {
        "symbol": "ETHUSDT",
        "factors": {
            "zscore": 0.1,
            "ROC5": 0.001,
            "ROC20": -0.002,
            "PRICE_VOLATILITY_20": 0.08,  # very high vol without trend
        },
        "order_flow": {
            "cvd": 50.0,
        },
        "risk_metrics": {
            "var_95_pct": 0.04,
            "current_drawdown_pct": 0.08,
            "liquidation_distance_pct": 0.20,
            "kelly_fraction": 0.02,
        },
    }
    decision = engine.deliberate_regime_and_trade(state)

    assert decision.action == "HOLD"
    assert decision.regime == "HIGH_VOL_CHOP"
    assert decision.suggested_sizing_pct <= 0.05


def test_mock_native_mode_and_fallback():
    # If native model is requested but weights are missing, it falls back gracefully
    engine = THX02DecisionEngine(mode=ExecutionMode.NATIVE, fallback_to_ensemble=True)
    assert engine.effective_mode in (ExecutionMode.NATIVE, ExecutionMode.DETERMINISTIC_ENSEMBLE)

    # Calling a decision should succeed regardless
    res = engine.ask_choice({"zscore": 1.0}, "Select action", ["BUY", "SELL", "HOLD"])
    assert res["best_choice"] in ["BUY", "SELL", "HOLD"]

    # If native mode is forced with fallback_to_ensemble=False and weights not present, raise RuntimeError
    with pytest.raises(RuntimeError, match="Native THX-02 runtime unavailable"):
        strict_engine = THX02DecisionEngine(
            mode=ExecutionMode.NATIVE,
            fallback_to_ensemble=False,
            model_path="/non/existent/path/weights.bin",
        )
        strict_engine.ask_choice({}, "Question?", ["A", "B"])


def test_edge_cases_empty_and_extreme_state():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)

    # Empty state does not crash
    dec = engine.deliberate_regime_and_trade({})
    assert dec.action == "HOLD"
    assert dec.conviction >= 0.0

    # Extreme volatility state
    extreme_state = {
        "factors": {"PRICE_VOLATILITY_20": 1000.0, "zscore": 999.0},
        "risk_metrics": {"var_95_pct": 0.99, "current_drawdown_pct": 0.90},
    }
    dec_extreme = engine.deliberate_regime_and_trade(extreme_state)
    assert dec_extreme.risk_cleared is False
    assert dec_extreme.action == "HOLD"


def test_committee_integration_with_thx02():
    engine = THX02DecisionEngine(mode=ExecutionMode.DETERMINISTIC_ENSEMBLE)
    committee = HedgeFundCommittee(decision_engine=engine)

    market_context = {
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
            "var_95_pct": 0.03,
            "current_drawdown_pct": 0.04,
            "liquidation_distance_pct": 0.35,
            "kelly_fraction": 0.20,
        },
    }

    decision = committee.deliberate_sync("BTCUSDT", market_context)
    assert decision.action == "BUY"
    assert "THX-02 Thinking Reasoning" in decision.synthesis_memo
    assert "Regime:" in decision.synthesis_memo

    # Verify that Risk Officer VETO strictly overrides THX-02
    market_context["risk_metrics"]["var_95_pct"] = 0.09
    veto_decision = committee.deliberate_sync("BTCUSDT", market_context)
    assert veto_decision.risk_veto is True
    assert veto_decision.action == "HOLD"
    assert veto_decision.suggested_sizing_pct == 0.0
