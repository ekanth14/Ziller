import math
import pytest
from core.quant.stage1_data import (
    compute_log_returns,
    compute_annualized_vol,
    compute_ewma_vol,
    compute_atr,
    filter_bad_ticks,
    verify_no_lookahead,
)

def test_log_returns_additive():
    prices = [100.0, 110.0, 100.0]
    r = compute_log_returns(prices)
    assert len(r) == 2
    assert math.isclose(r[0], math.log(1.10), rel_tol=1e-5)
    assert math.isclose(r[1], math.log(100.0 / 110.0), rel_tol=1e-5)
    assert math.isclose(sum(r), 0.0, abs_tol=1e-7)

def test_log_returns_invalid():
    with pytest.raises(ValueError):
        compute_log_returns([100.0, -5.0])
    with pytest.raises(ValueError):
        compute_log_returns([0.0, 100.0])

def test_annualized_vol_crypto_365():
    daily_vol = 0.01
    annual_vol = compute_annualized_vol(daily_vol, bars_per_year=365)
    assert math.isclose(annual_vol, daily_vol * math.sqrt(365), rel_tol=1e-4)

    # Stocks 252 days: 1% daily = 15.87%
    annual_vol_stocks = compute_annualized_vol(daily_vol, bars_per_year=252)
    assert math.isclose(annual_vol_stocks, daily_vol * math.sqrt(252), rel_tol=1e-4)

def test_ewma_vol_shock():
    returns = [0.02, -0.05]
    vols = compute_ewma_vol(returns, lambda_param=0.94)
    assert len(vols) == 2
    assert vols[1] > vols[0]
    assert math.isclose(vols[0], 0.02, rel_tol=1e-5)
    expected_sigma2_1 = 0.94 * (0.02 ** 2) + 0.06 * ((-0.05) ** 2)
    assert math.isclose(vols[1], math.sqrt(expected_sigma2_1), rel_tol=1e-5)

def test_atr_with_gaps():
    atr = compute_atr(highs=[100.0, 105.0], lows=[98.0, 101.0], closes=[99.0, 104.0], period=1)
    assert atr[-1] == 6.0

def test_bad_tick_filter():
    # 20 regular ticks around 0.1% volatility, then a 9% shock tick
    returns = [0.001, -0.001, 0.0015, -0.0008, 0.0012] * 4 + [0.09]
    flags = filter_bad_ticks(returns, threshold_sigma=6.0)
    assert flags[-1] is True
    assert flags[0] is False

def test_no_lookahead_validator():
    assert verify_no_lookahead(bar_index=100, signal_time=100, fill_time=101) is True
    assert verify_no_lookahead(bar_index=100, signal_time=100, fill_time=100) is False
