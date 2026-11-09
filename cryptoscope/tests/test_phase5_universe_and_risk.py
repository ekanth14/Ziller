"""Tests for Phase 5: Universe Manager, Dynamic Cost Model, and Portfolio Risk."""

import pytest
import pandas as pd
import numpy as np

from cryptoscope.research.multi_coin.universe_manager import (
    PointInTimeUniverseManager,
    UniverseConfig,
    MS_PER_DAY,
    MS_PER_HOUR,
)
from cryptoscope.research.multi_coin.cost_model import (
    DynamicCostModel,
    CostModelCalibration,
)
from cryptoscope.research.multi_coin.portfolio_risk import (
    MultiCoinPortfolioRiskManager,
    PortfolioRiskConfig,
)


# ==============================================================================
# Phase 5.1 Universe Manager Tests
# ==============================================================================

def test_universe_structural_exclusions():
    mgr = PointInTimeUniverseManager()
    assert mgr.is_excluded_category("BTCUPUSDT") == "leveraged_token_UP"
    assert mgr.is_excluded_category("ETHBEARUSDT") == "leveraged_token_BEAR"
    assert mgr.is_excluded_category("BUSDUSDT") == "stablecoin"
    assert mgr.is_excluded_category("FDUSDUSDT") == "stablecoin"
    assert mgr.is_excluded_category("BTCUSDT") is None
    assert mgr.is_excluded_category("SOLUSDT") is None


def test_universe_point_in_time_qualification(tmp_path):
    config = UniverseConfig(
        min_30d_quote_volume_usd=1_000_000.0,
        min_depth_1pct_usd=10_000.0,
        min_listing_age_days=30,
        account_size_usd=1000.0,
    )
    mgr = PointInTimeUniverseManager(config=config, parquet_dir=tmp_path)

    # 1. Create a dummy dataframe for BTCUSDT with 60 days of hourly bars
    base_ts = 1700000000000
    n_hours = 60 * 24
    times = [base_ts + i * MS_PER_HOUR for i in range(n_hours)]
    df_btc = pd.DataFrame({
        "open_time": times,
        "open": [30000.0] * n_hours,
        "high": [30100.0] * n_hours,
        "low": [29900.0] * n_hours,
        "close": [30000.0] * n_hours,
        "volume": [10.0] * n_hours,
        "quote_volume": [300000.0] * n_hours,  # $300k/hr = $216M / 30d
        "close_time": [t + MS_PER_HOUR - 1 for t in times],
        "trades": [500] * n_hours,
        "taker_buy_volume": [5.0] * n_hours,
        "taker_buy_quote_volume": [150000.0] * n_hours,
    })
    mgr._klines_cache["BTCUSDT"] = df_btc
    mgr._first_seen_ms["BTCUSDT"] = times[0]
    mgr._last_seen_ms["BTCUSDT"] = times[-1]

    # At day 15 (less than 30 days listing age): should fail age check
    as_of_day15 = base_ts + 15 * MS_PER_DAY
    eligible, reason, _ = mgr.evaluate_symbol_eligibility("BTCUSDT", as_of_day15)
    assert not eligible
    assert "listing_age_too_young" in reason

    # At day 45 (45 days listing age, ample volume): should PASS
    as_of_day45 = base_ts + 45 * MS_PER_DAY
    eligible, reason, metrics = mgr.evaluate_symbol_eligibility("BTCUSDT", as_of_day45)
    assert eligible
    assert reason is None
    assert metrics["listing_age_days"] == 45.0
    assert metrics["quote_vol_30d"] > 1_000_000.0

    # At day 80 (asset stopped trading at day 60): should fail delisted_or_halted
    as_of_day80 = base_ts + 80 * MS_PER_DAY
    eligible, reason, _ = mgr.evaluate_symbol_eligibility("BTCUSDT", as_of_day80)
    assert not eligible
    assert reason == "delisted_or_halted"


# ==============================================================================
# Phase 5.2 Dynamic Cost Model Tests
# ==============================================================================

def test_dynamic_cost_model_spread_and_impact():
    cost_model = DynamicCostModel()

    # Small order on deep liquidity ($50 on $100M volume)
    res_small = cost_model.calculate_execution(
        symbol="BTCUSDT",
        side="BUY",
        order_size_usd=50.0,
        price=80000.0,
        bar_high=80500.0,
        bar_low=79500.0,
        bar_close=80000.0,
        volume_24h_usd=100_000_000.0,
    )
    assert res_small.effective_price > 80000.0  # Buy pays slippage
    assert res_small.exchange_fee_usd == pytest.approx(50.0 * 0.00075, rel=1e-3)
    assert res_small.impact_slippage_bps >= 1.0  # Latency floor

    # Large order on thin liquidity ($10,000 on $500k volume)
    res_large = cost_model.calculate_execution(
        symbol="SOLUSDT",
        side="BUY",
        order_size_usd=10000.0,
        price=150.0,
        bar_high=155.0,
        bar_low=145.0,
        bar_close=150.0,
        volume_24h_usd=500_000.0,
    )
    # Impact on thin liquidity must be noticeably higher
    assert res_large.impact_slippage_bps > res_small.impact_slippage_bps
    assert res_large.total_cost_bps > res_small.total_cost_bps


def test_cost_model_maker_vs_taker():
    cost_model = DynamicCostModel()
    res_taker = cost_model.calculate_execution(
        symbol="BTCUSDT", side="SELL", order_size_usd=100.0, price=80000.0,
        bar_high=80500.0, bar_low=79500.0, bar_close=80000.0, volume_24h_usd=50_000_000.0,
        is_maker=False,
    )
    res_maker = cost_model.calculate_execution(
        symbol="BTCUSDT", side="SELL", order_size_usd=100.0, price=80000.0,
        bar_high=80500.0, bar_low=79500.0, bar_close=80000.0, volume_24h_usd=50_000_000.0,
        is_maker=True,
    )
    # Maker has 0 slippage and lower maker fee (0.02% vs 0.075%)
    assert res_maker.total_slippage_bps == 0.0
    assert res_maker.effective_price == 80000.0
    assert res_maker.exchange_fee_usd < res_taker.exchange_fee_usd


def test_cost_model_sensitivity_stress_monotonicity():
    cost_model = DynamicCostModel()
    matrix = cost_model.run_sensitivity_analysis(order_sizes_usd=[100.0], multipliers=[0.5, 1.0, 2.0])
    
    # Verify that higher stress multiplier results in higher or equal total cost bps
    btc_runs = [m for m in matrix if m["symbol"] == "BTCUSDT"]
    assert btc_runs[0]["total_cost_bps"] <= btc_runs[1]["total_cost_bps"] <= btc_runs[2]["total_cost_bps"]


# ==============================================================================
# Phase 5.3 Multi-Coin Portfolio Risk Tests
# ==============================================================================

def test_portfolio_risk_concurrent_positions_limit():
    config = PortfolioRiskConfig(max_concurrent_positions=3)
    risk = MultiCoinPortfolioRiskManager(initial_nav=1000.0, config=config)

    # Fill 3 positions
    risk.record_fill("BTCUSDT", "BUY", 100.0)
    risk.record_fill("ETHUSDT", "BUY", 100.0)
    risk.record_fill("SOLUSDT", "BUY", 100.0)

    # 4th position should be vetoed
    check = risk.evaluate_order("AVAXUSDT", "BUY", requested_size_usd=50.0, est_depth_1pct_usd=50000.0)
    assert not check.approved
    assert "max_concurrent_positions" in check.veto_reason
    assert risk.trigger_counts["max_positions"] == 1


def test_portfolio_risk_per_coin_and_cluster_caps():
    config = PortfolioRiskConfig(
        max_per_coin_pct=0.25,          # $250 max per coin on $1000 NAV
        max_cluster_exposure_pct=0.40,  # $400 max in any cluster
    )
    risk = MultiCoinPortfolioRiskManager(initial_nav=1000.0, config=config)

    # Request $300 for BTC (exceeds 25% = $250 per coin limit) -> downscales to $250
    check = risk.evaluate_order("BTCUSDT", "BUY", requested_size_usd=300.0, est_depth_1pct_usd=100000.0)
    assert check.approved
    assert check.approved_size_usd == 250.0
    assert "per_coin_cap" in check.applied_caps

    risk.record_fill("BTCUSDT", "BUY", 250.0)

    # Now request $250 for ETH (CORE cluster now has $250 BTC; max cluster is $400, so only $150 remaining)
    check2 = risk.evaluate_order("ETHUSDT", "BUY", requested_size_usd=250.0, est_depth_1pct_usd=100000.0)
    assert check2.approved
    assert check2.approved_size_usd == 150.0  # Capped by cluster exposure limit
    assert "cluster_limit" in check2.applied_caps


def test_portfolio_risk_drawdown_circuit_breaker():
    config = PortfolioRiskConfig(max_drawdown_halt_pct=0.10)  # 10% halt
    risk = MultiCoinPortfolioRiskManager(initial_nav=1000.0, config=config)

    # NAV drops from $1000 to $890 (11% drawdown)
    risk.update_equity(current_nav=890.0, timestamp_ms=1700000000000)
    assert risk.drawdown_halt_active

    # New order should be strictly vetoed
    check = risk.evaluate_order("BTCUSDT", "BUY", requested_size_usd=50.0, est_depth_1pct_usd=100000.0)
    assert not check.approved
    assert "drawdown_halt" in check.veto_reason
