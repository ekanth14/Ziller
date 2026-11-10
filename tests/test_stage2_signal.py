import math
import pytest
from core.quant.stage2_signal import (
    compute_zscore,
    compute_ema,
    compute_momentum_12_1,
    compute_rsi,
    compute_order_book_imbalance,
    compute_funding_carry_apr,
)

def test_zscore_calculation():
    # 19 values of 100, then 1 value of 109. Mean = 100.45, std ≈ 2.01 -> z ≈ 4.25
    vals = [100.0] * 19 + [109.0]
    z = compute_zscore(vals, window=20)
    assert len(z) == len(vals)
    assert z[-1] > 2.0

def test_ema_alpha():
    # n=20 -> alpha = 2/(21) ≈ 0.095238
    vals = [10.0] * 20 + [20.0]
    ema = compute_ema(vals, period=20)
    assert ema[0] == 10.0
    assert ema[-1] > 10.0
    assert ema[-1] < 20.0

def test_momentum_12_1():
    # 120 a month ago (t-21), 100 a year ago (t-252): 120/100 - 1 = +20%
    # Length 253: index 0 is t-252 (100.0), index 231 is t-21 (120.0)
    prices = [100.0] * 231 + [120.0] * 22
    mom = compute_momentum_12_1(prices, lag_short=21, lag_long=252)
    assert pytest.approx(mom, 0.01) == 0.20

def test_rsi_bounds():
    # 30 rising prices -> RSI should be high (>70)
    prices = [100.0 + i for i in range(30)]
    rsi = compute_rsi(prices, period=14)
    assert len(rsi) == 30
    assert rsi[-1] > 70.0

    # 30 falling prices -> RSI should be low (<30)
    prices_down = [100.0 - i for i in range(30)]
    rsi_down = compute_rsi(prices_down, period=14)
    assert rsi_down[-1] < 30.0

def test_order_book_imbalance():
    # 900 on bid, 300 on ask: (900-300)/(900+300) = 600/1200 = 0.5
    imb = compute_order_book_imbalance(bid_qty=900.0, ask_qty=300.0)
    assert pytest.approx(imb, 1e-4) == 0.5

    # 0 liquidity handles safely
    assert compute_order_book_imbalance(0.0, 0.0) == 0.0

def test_funding_carry_apr():
    # 0.01% per 8h -> 0.0001 * 3 * 365 = 10.95%
    apr = compute_funding_carry_apr(funding_rate_8h=0.0001)
    assert pytest.approx(apr, 1e-4) == 0.1095
