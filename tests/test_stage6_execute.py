import pytest
from core.quant.stage6_execute import (
    compute_spread_cost,
    compute_microprice,
    compute_square_root_impact,
    compute_vwap,
    compute_slippage,
    compute_round_trip_fee,
)

def test_spread_cost():
    # 99.95 / 100.05 -> mid 100.0, spread 0.10 (0.1%), half 0.05%
    spread, half = compute_spread_cost(bid=99.95, ask=100.05)
    assert pytest.approx(spread, 1e-4) == 0.001
    assert pytest.approx(half, 1e-4) == 0.0005

def test_microprice():
    # 100.00 x 900 bid, 100.10 x 300 ask -> (100*300 + 100.1*900)/1200 = 100.075
    p_micro = compute_microprice(bid_price=100.0, bid_qty=900.0, ask_price=100.10, ask_qty=300.0)
    assert pytest.approx(p_micro, 1e-4) == 100.075

    # Zero liquidity fallback to mid price when last_price not provided
    assert compute_microprice(100.0, 0.0, 100.1, 0.0) == 100.05

    # Zero liquidity fallback to last_price when provided
    assert compute_microprice(100.0, 0.0, 100.1, 0.0, last_price=100.02) == 100.02

def test_square_root_impact():
    # sigma 2%, order size 1% of daily volume: impact ≈ 0.02 * sqrt(0.01) = 0.02 * 0.1 = 0.002 (0.2%)
    impact = compute_square_root_impact(volatility=0.02, order_qty=100.0, daily_volume=10000.0)
    assert pytest.approx(impact, 1e-4) == 0.002

def test_vwap():
    # 100 @ 10.0, 200 @ 10.5 -> total = 1000 + 2100 = 3100 / 300 = 10.3333
    vwap = compute_vwap([(10.0, 100.0), (10.5, 200.0)])
    assert pytest.approx(vwap, 1e-4) == 10.3333

    # Empty trades fallback
    assert compute_vwap([]) == 0.0

def test_slippage():
    # Expected 100, filled 100.08: 0.08%
    slip = compute_slippage(expected_price=100.0, filled_price=100.08)
    assert pytest.approx(slip, 1e-5) == 0.0008

def test_maker_taker_fee():
    # Taker 0.05% -> round trip = 0.10%
    assert pytest.approx(compute_round_trip_fee(0.0005), 1e-5) == 0.0010
