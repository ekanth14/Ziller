import pytest
from core.quant.stage7_risk import (
    compute_max_drawdown,
    compute_recovery_gain,
    compute_var_95,
    compute_portfolio_volatility,
    compute_risk_of_ruin,
    check_kill_switch,
)

def test_max_drawdown():
    # Peak $12k, low $9k: DD = (12k - 9k)/12k = 25%
    series = [10000.0, 12000.0, 11000.0, 9000.0, 10500.0]
    dd, peak, trough = compute_max_drawdown(series)
    assert pytest.approx(dd, 1e-4) == 0.25
    assert peak == 12000.0
    assert trough == 9000.0

    # Empty or single item
    assert compute_max_drawdown([1000.0]) == (0.0, 1000.0, 1000.0)

def test_recovery_math():
    # -20% needs +25%; -50% needs +100%
    assert pytest.approx(compute_recovery_gain(0.20), 1e-4) == 0.25
    assert pytest.approx(compute_recovery_gain(0.50), 1e-4) == 1.00
    assert compute_recovery_gain(1.00) == float("inf")

def test_var_95():
    # $10k at 3% daily sigma: 1.645 * 0.03 * 10000 = $493.5
    var = compute_var_95(portfolio_value=10000.0, daily_vol=0.03)
    assert pytest.approx(var, 0.5) == 493.5

def test_portfolio_volatility_two_assets():
    # 50/50, both 20% vol, rho 0.5: sigma_p = sqrt(0.5^2*0.04 + 0.5^2*0.04 + 2*0.5*0.5*0.04*0.5) = sqrt(0.03) ≈ 17.32%
    weights = [0.5, 0.5]
    cov = [[0.04, 0.02], [0.02, 0.04]]
    port_vol = compute_portfolio_volatility(weights, cov)
    assert pytest.approx(port_vol, 1e-3) == 0.1732

def test_risk_of_ruin():
    # p 0.55, N 20: ((1-0.55)/0.55)^20 = (0.45/0.55)^20 ≈ 0.01807 (1.81%)
    expected_ruin = (0.45 / 0.55) ** 20
    ruin = compute_risk_of_ruin(win_prob=0.55, units=20)
    assert pytest.approx(ruin, 1e-4) == expected_ruin

    # p <= 0.5: ruin is 100% (1.0)
    assert compute_risk_of_ruin(win_prob=0.50, units=20) == 1.0

def test_kill_switch_trip():
    # Peak $10k, max DD 15%: stop under $8,500
    assert check_kill_switch(current_equity=8400.0, peak_equity=10000.0, max_allowed_dd=0.15) is True
    assert check_kill_switch(current_equity=8600.0, peak_equity=10000.0, max_allowed_dd=0.15) is False
