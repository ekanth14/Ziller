import pytest
from core.quant.microstructure.market_making import (
    compute_reservation_price,
    compute_optimal_spread,
    compute_avellaneda_stoikov_quotes,
    compute_inventory_skewed_sizes,
    AvellanedaStoikovMarketMaker,
)

def test_reservation_price_neutral_inventory():
    # When inventory q == 0, reservation price equals mid price
    mid = 100.0
    res = compute_reservation_price(mid_price=mid, inventory=0.0, gamma=0.1, volatility=0.02, time_horizon=1.0)
    assert res == pytest.approx(100.0)

def test_reservation_price_long_inventory():
    # When q > 0, reservation price is LESS than mid price (urgency to sell)
    mid = 100.0
    res = compute_reservation_price(mid_price=mid, inventory=5.0, gamma=0.1, volatility=0.02, time_horizon=1.0)
    # r = 100 - 5 * 0.1 * (0.02^2) * 1.0 = 100 - 5 * 0.1 * 0.0004 = 100 - 0.0002 = 99.9998
    assert res < mid
    assert res == pytest.approx(99.9998)

def test_reservation_price_short_inventory():
    # When q < 0, reservation price is GREATER than mid price (urgency to buy)
    mid = 100.0
    res = compute_reservation_price(mid_price=mid, inventory=-5.0, gamma=0.1, volatility=0.02, time_horizon=1.0)
    assert res > mid
    assert res == pytest.approx(100.0002)

def test_optimal_spread_positive_and_monotonic():
    # Optimal spread increases with higher volatility
    s1 = compute_optimal_spread(gamma=0.1, volatility=0.01, kappa=1.5, time_horizon=1.0)
    s2 = compute_optimal_spread(gamma=0.1, volatility=0.05, kappa=1.5, time_horizon=1.0)
    assert s1 > 0
    assert s2 > s1

def test_avellaneda_stoikov_quotes_structure():
    quotes = compute_avellaneda_stoikov_quotes(
        mid_price=50000.0,
        inventory=2.0,
        gamma=0.01,
        volatility=0.03,
        kappa=1.2,
        time_horizon=1.0,
    )
    assert "reservation_price" in quotes
    assert "optimal_spread" in quotes
    assert "bid_price" in quotes
    assert "ask_price" in quotes
    assert quotes["bid_price"] < quotes["reservation_price"] < quotes["ask_price"]
    assert quotes["ask_price"] > quotes["bid_price"]
    assert quotes["optimal_spread"] == pytest.approx(quotes["ask_price"] - quotes["bid_price"])

def test_inventory_skewed_sizes():
    # Neutral inventory
    bid_sz, ask_sz = compute_inventory_skewed_sizes(target_order_size=1.0, inventory=0.0, max_inventory=10.0)
    assert bid_sz == pytest.approx(1.0)
    assert ask_sz == pytest.approx(1.0)

    # Long inventory (q = 5, max = 10) -> bid size reduced to 0.5, ask size boosted to 1.5
    bid_sz, ask_sz = compute_inventory_skewed_sizes(target_order_size=1.0, inventory=5.0, max_inventory=10.0)
    assert bid_sz == pytest.approx(0.5)
    assert ask_sz == pytest.approx(1.5)

    # Max long inventory (q = 10) -> bid size drops to 0.0
    bid_sz, ask_sz = compute_inventory_skewed_sizes(target_order_size=1.0, inventory=10.0, max_inventory=10.0)
    assert bid_sz == pytest.approx(0.0)
    assert ask_sz == pytest.approx(2.0)

def test_market_maker_class_stateful_flow():
    mm = AvellanedaStoikovMarketMaker(
        gamma=0.05,
        kappa=1.5,
        time_horizon=1.0,
        max_inventory=5.0,
        target_order_size=1.0,
    )
    assert mm.inventory == 0.0

    quotes0 = mm.compute_quotes(mid_price=100.0, volatility=0.02)
    assert quotes0["inventory"] == 0.0
    assert quotes0["bid_size"] == 1.0
    assert quotes0["ask_size"] == 1.0

    # Simulating long fill (+2 units)
    mm.update_inventory(2.0)
    assert mm.inventory == 2.0
    quotes1 = mm.compute_quotes(mid_price=100.0, volatility=0.02)
    assert quotes1["reservation_price"] < 100.0
    assert quotes1["bid_size"] < 1.0
    assert quotes1["ask_size"] > 1.0

def test_market_making_safety_guards():
    # Mid price <= 0 raises ValueError
    with pytest.raises(ValueError, match="mid_price must be positive"):
        compute_reservation_price(mid_price=-10.0, inventory=0.0, gamma=0.1, volatility=0.01)

    # Gamma <= 0 raises ValueError
    with pytest.raises(ValueError, match="gamma must be positive"):
        compute_optimal_spread(gamma=0.0, volatility=0.01, kappa=1.0)
