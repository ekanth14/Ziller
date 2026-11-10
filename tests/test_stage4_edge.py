import pytest
from core.quant.stage4_edge import (
    compute_expected_value,
    compute_breakeven_win_rate,
    compute_expectancy_in_r,
    compute_profit_factor,
    compute_bayesian_win_rate,
    compute_net_edge,
)

def test_expected_value():
    # 40% win, $300 win, $150 loss: 0.4*300 - 0.6*150 = 120 - 90 = +$30
    ev = compute_expected_value(win_prob=0.4, avg_win=300.0, avg_loss=150.0)
    assert pytest.approx(ev, 1e-4) == 30.0

def test_breakeven_win_rate():
    # Win 2R, lose 1R: W/L = 2 -> 1 / (1 + 2) = 33.3%
    be = compute_breakeven_win_rate(avg_win=200.0, avg_loss=100.0)
    assert pytest.approx(be, 1e-4) == 1.0 / 3.0

def test_expectancy_in_r():
    # 40% win at 3R: 0.4 * 3 - 0.6 * 1 = 1.2 - 0.6 = +0.6R
    exp_r = compute_expectancy_in_r(win_prob=0.4, r_win=3.0)
    assert pytest.approx(exp_r, 1e-4) == 0.6

def test_profit_factor():
    # $6,000 won, $4,000 lost: PF = 1.5
    pf = compute_profit_factor(gross_wins=6000.0, gross_losses=4000.0)
    assert pytest.approx(pf, 1e-4) == 1.5
    # Zero loss edge case
    assert compute_profit_factor(gross_wins=500.0, gross_losses=0.0) == float("inf")

def test_bayesian_win_rate():
    # Prior Beta(1,1), 7 wins in 10: (1+7)/(1+1+10) = 8/12 = 66.7%
    p_hat = compute_bayesian_win_rate(wins=7, n=10, alpha=1.0, beta=1.0)
    assert pytest.approx(p_hat, 1e-4) == 8.0 / 12.0

def test_net_edge():
    # 0.25% gross, 0.1% fee + 0.05% slip per side: net = 0.0025 - 2*(0.0010 + 0.0005) = -0.05%
    net = compute_net_edge(gross_edge=0.0025, fee_rate=0.0010, slippage_rate=0.0005)
    assert pytest.approx(net, 1e-5) == -0.0005
