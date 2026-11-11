import pytest
from core.quant.levels.level9_microstructure import (
    compute_mid_price,
    compute_spreads,
    compute_order_book_imbalance,
    compute_multilevel_imbalance,
    compute_microprice,
    compute_square_root_impact,
    compute_vwap,
    compute_twap,
    compute_implementation_shortfall,
    compute_avellaneda_stoikov,
)

# ---------------------------------------------------------
# Formula 9.1: Spread & Mid
# ---------------------------------------------------------
def test_mid_and_spreads():
    bid, ask = 99.95, 100.05
    mid = compute_mid_price(bid, ask)
    assert pytest.approx(mid, 1e-5) == 100.0

    spreads = compute_spreads(bid, ask)
    assert pytest.approx(spreads["mid"], 1e-5) == 100.0
    assert pytest.approx(spreads["abs_spread"], 1e-5) == 0.10
    # Relative spread: 0.10 / 100.0 = 0.001 (0.1% or 10 bps)
    assert pytest.approx(spreads["rel_spread"], 1e-5) == 0.001
    assert pytest.approx(spreads["half_spread"], 1e-5) == 0.0005

def test_spread_zero_and_crossed_book():
    # Zero price or non-positive
    assert compute_mid_price(0.0, 100.0) == 0.0
    # Crossed book (bid > ask)
    spreads = compute_spreads(105.0, 100.0)
    assert spreads["abs_spread"] == 0.0
    assert spreads["rel_spread"] == 0.0

# ---------------------------------------------------------
# Formula 9.2: Order Book Imbalance & Microprice
# ---------------------------------------------------------
def test_order_book_imbalance():
    # 800 bid, 200 ask -> I = (800 - 200) / 1000 = +0.60 (heavy buy pressure)
    imb = compute_order_book_imbalance(bid_qty=800.0, ask_qty=200.0)
    assert pytest.approx(imb, 1e-4) == 0.60

    # Equal sizes -> 0.0
    assert compute_order_book_imbalance(500.0, 500.0) == 0.0

    # 100 bid, 900 ask -> I = -0.80 (heavy sell pressure)
    assert pytest.approx(compute_order_book_imbalance(100.0, 900.0), 1e-4) == -0.80

    # Empty book guard
    assert compute_order_book_imbalance(0.0, 0.0) == 0.0

def test_multilevel_imbalance():
    bids = [(100.0, 100.0), (99.9, 200.0), (99.8, 300.0)]
    asks = [(100.1, 50.0), (100.2, 50.0), (100.3, 100.0)]
    # Total bids = 600, Total asks = 200 -> (600 - 200) / 800 = 0.50
    imb = compute_multilevel_imbalance(bids, asks, depth=3)
    assert pytest.approx(imb, 1e-4) == 0.50

def test_microprice_weighting_and_fallback():
    # Bid 100.0 x 900, Ask 100.10 x 300
    # P_micro = (100.0 * 300 + 100.10 * 900) / 1200 = (30000 + 90090) / 1200 = 100.075
    p_micro = compute_microprice(bid_price=100.0, bid_qty=900.0, ask_price=100.10, ask_qty=300.0)
    assert pytest.approx(p_micro, 1e-4) == 100.075

    # Safe fallback on thin order book:
    # 1) When last_price is provided, microprice falls back to last_price
    p_fallback_last = compute_microprice(
        bid_price=100.0,
        bid_qty=0.0,
        ask_price=100.10,
        ask_qty=0.0,
        last_price=100.02,
    )
    assert p_fallback_last == 100.02

    # 2) When last_price is None, falls back to mid price
    p_fallback_mid = compute_microprice(
        bid_price=100.0,
        bid_qty=0.0,
        ask_price=100.10,
        ask_qty=0.0,
        last_price=None,
    )
    assert pytest.approx(p_fallback_mid, 1e-4) == 100.05

# ---------------------------------------------------------
# Formula 9.3: Square-Root Impact
# ---------------------------------------------------------
def test_square_root_impact():
    # Volatility = 2% (0.02), Order = 100, Daily Volume = 10,000, c = 1.0, Price = $100
    # Impact = c * sigma * sqrt(Q / V) = 1.0 * 0.02 * sqrt(100 / 10000) = 0.02 * 0.10 = 0.002 (0.2%)
    # Absolute impact: 100 * 0.002 = $0.20
    # Expected execution: $100.20
    res = compute_square_root_impact(
        volatility=0.02,
        order_qty=100.0,
        market_volume=10000.0,
        impact_constant=1.0,
        current_price=100.0,
    )
    assert pytest.approx(res["relative_impact"], 1e-5) == 0.002
    assert pytest.approx(res["absolute_impact"], 1e-4) == 0.20
    assert pytest.approx(res["expected_execution_price"], 1e-4) == 100.20

def test_square_root_impact_zero_guards():
    res = compute_square_root_impact(volatility=0.02, order_qty=0.0, market_volume=10000.0)
    assert res["relative_impact"] == 0.0
    assert res["absolute_impact"] == 0.0

    res_novol = compute_square_root_impact(volatility=0.02, order_qty=100.0, market_volume=0.0)
    assert res_novol["relative_impact"] == 0.0

# ---------------------------------------------------------
# Formula 9.4: VWAP, TWAP & Implementation Shortfall
# ---------------------------------------------------------
def test_vwap_and_twap():
    trades = [(100.0, 10.0), (102.0, 30.0)]
    # Sum(p * q) = 1000 + 3060 = 4060 / 40 = 101.5
    vwap = compute_vwap(trades)
    assert pytest.approx(vwap, 1e-4) == 101.5

    # TWAP: unweighted average of prices
    prices = [100.0, 102.0, 104.0]
    twap = compute_twap(prices)
    assert pytest.approx(twap, 1e-4) == 102.0

def test_implementation_shortfall():
    # Decision price: 100.0, Executed price: 100.15, Side: BUY, Qty: 100
    # Shortfall: 100.15 - 100.0 = 0.15 per unit
    # bps: 0.15 / 100.0 * 10000 = 15 bps
    # Total cost: 0.15 * 100 = $15.0
    res_buy = compute_implementation_shortfall(decision_price=100.0, execution_price=100.15, side="BUY", quantity=100.0)
    assert pytest.approx(res_buy["shortfall"], 1e-4) == 0.15
    assert pytest.approx(res_buy["shortfall_bps"], 1e-2) == 15.0
    assert pytest.approx(res_buy["total_cost"], 1e-4) == 15.0

    # Shortfall for SELL: Decision: 100.0, Executed: 99.80 -> shortfall = 100.0 - 99.80 = 0.20
    res_sell = compute_implementation_shortfall(decision_price=100.0, execution_price=99.80, side="SELL", quantity=50.0)
    assert pytest.approx(res_sell["shortfall"], 1e-4) == 0.20
    assert pytest.approx(res_sell["total_cost"], 1e-4) == 10.0

# ---------------------------------------------------------
# Formula 9.5: Avellaneda-Stoikov Market Making
# ---------------------------------------------------------
def test_avellaneda_stoikov_inventory_skew():
    s = 100.0        # mid price
    gamma = 0.1      # risk aversion
    sigma = 0.05     # asset vol
    t_rem = 1.0      # time horizon
    kappa = 1.5      # liquidity parameter

    # 1. Neutral inventory (q = 0)
    res_neutral = compute_avellaneda_stoikov(mid_price=s, inventory=0.0, gamma=gamma, sigma=sigma, time_horizon=t_rem, kappa=kappa)
    assert pytest.approx(res_neutral["reservation_price"], 1e-4) == 100.0
    # Optimal spread: gamma * sigma^2 * (T - t) + (2/gamma)*ln(1 + gamma/kappa)
    # = 0.1 * 0.0025 * 1.0 + (2 / 0.1) * ln(1 + 0.1 / 1.5)
    # = 0.00025 + 20 * ln(1.066667) = 0.00025 + 20 * 0.06453856 = 0.00025 + 1.29077 = 1.29102
    assert pytest.approx(res_neutral["optimal_spread"], 1e-3) == 1.291
    # Bid / Ask symmetric around mid
    assert pytest.approx(res_neutral["ask_quote"] - s, 1e-3) == res_neutral["half_spread"]
    assert pytest.approx(s - res_neutral["bid_quote"], 1e-3) == res_neutral["half_spread"]

    # 2. Long inventory (q = +5): reservation price should be LOWER than mid to shed inventory
    res_long = compute_avellaneda_stoikov(mid_price=s, inventory=5.0, gamma=gamma, sigma=sigma, time_horizon=t_rem, kappa=kappa)
    assert res_long["reservation_price"] < s
    assert res_long["bid_quote"] < res_neutral["bid_quote"]
    assert res_long["ask_quote"] < res_neutral["ask_quote"]

    # 3. Short inventory (q = -5): reservation price should be HIGHER than mid
    res_short = compute_avellaneda_stoikov(mid_price=s, inventory=-5.0, gamma=gamma, sigma=sigma, time_horizon=t_rem, kappa=kappa)
    assert res_short["reservation_price"] > s
    assert res_short["bid_quote"] > res_neutral["bid_quote"]
    assert res_short["ask_quote"] > res_neutral["ask_quote"]
