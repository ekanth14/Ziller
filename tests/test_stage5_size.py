import pytest
from core.quant.stage5_size import (
    compute_risk_based_size,
    compute_kelly_criterion,
    compute_continuous_kelly,
    compute_volatility_target_weight,
    compute_risk_parity_weights,
    compute_liquidation_price,
)

def test_risk_based_size():
    # $10k, 1% risk ($100), entry 100, stop 95: size = 100 / |100-95| = 20 units
    size = compute_risk_based_size(equity=10000.0, risk_pct=0.01, entry=100.0, stop=95.0)
    assert pytest.approx(size, 1e-4) == 20.0

    # Stop equal to entry guard
    assert compute_risk_based_size(10000.0, 0.01, 100.0, 100.0) == 0.0

def test_kelly_criterion_half():
    # p 0.55, b 1: f* = 0.55 - 0.45/1 = 0.10 (10%), half Kelly = 5%
    f_half = compute_kelly_criterion(win_prob=0.55, payoff_b=1.0, fraction=0.5)
    assert pytest.approx(f_half, 1e-4) == 0.05

def test_continuous_kelly():
    # mu 10%, sigma 20% (var 0.04): f* = 0.10 / 0.04 = 2.5x, half = 1.25x
    lev = compute_continuous_kelly(mean_return=0.10, var_return=0.04, fraction=0.5)
    assert pytest.approx(lev, 1e-4) == 1.25

def test_vol_target_cap():
    # Target 15%, asset at 45%: weight = 15/45 = 1/3 ≈ 0.333
    w = compute_volatility_target_weight(target_vol=0.15, realized_vol=0.45, max_leverage=3.0)
    assert pytest.approx(w, 1e-4) == 1.0 / 3.0

    # Tiny vol capped at max_leverage
    w_huge = compute_volatility_target_weight(target_vol=0.15, realized_vol=0.01, max_leverage=3.0)
    assert w_huge == 3.0

def test_risk_parity_weights():
    # sigma 10% and 40%: inv 10 and 2.5 -> weights 80% and 20%
    w = compute_risk_parity_weights({"A": 0.10, "B": 0.40})
    assert pytest.approx(w["A"], 1e-4) == 0.80
    assert pytest.approx(w["B"], 1e-4) == 0.20

def test_liquidation_price():
    # Long: 10x, mmr 0.5%: 100 * (1 - 1/10 + 0.005) = 100 * 0.905 = 90.5 (-9.5%)
    liq_long = compute_liquidation_price(entry=100.0, leverage=10.0, mmr=0.005, is_long=True)
    assert pytest.approx(liq_long, 1e-4) == 90.5

    # Short: 10x, mmr 0.5%: 100 * (1 + 1/10 - 0.005) = 100 * 1.095 = 109.5 (+9.5%)
    liq_short = compute_liquidation_price(entry=100.0, leverage=10.0, mmr=0.005, is_long=False)
    assert pytest.approx(liq_short, 1e-4) == 109.5
