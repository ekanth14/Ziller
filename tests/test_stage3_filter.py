import pytest
from core.quant.stage3_filter import (
    compute_tstat_returns,
    compute_adf_test,
    compute_half_life,
    compute_hurst_exponent,
    compute_correlation_matrix,
    is_high_vol_regime,
)

def test_tstat_returns_formula():
    # Mean 0.1%/day, sigma 2%, 400 days: t = mean / (sigma / sqrt(n)) = 0.001 / (0.02 / 20) = 1.0
    returns = []
    for i in range(400):
        # alternating +0.021 and -0.019 -> mean = 0.001, variance = 0.0004 -> sigma = 0.02
        returns.append(0.021 if i % 2 == 0 else -0.019)
    t = compute_tstat_returns(returns)
    assert pytest.approx(t, 0.05) == 1.0

def test_adf_test_stationary():
    # Synthetic mean-reverting stationary series around 100
    series = [100.0]
    for i in range(250):
        prev = series[-1]
        noise = 1.0 if i % 2 == 0 else -1.0
        series.append(prev - 0.3 * (prev - 100.0) + noise)
    stat, is_stat = compute_adf_test(series)
    assert stat < -2.86
    assert is_stat is True

def test_half_life_mean_reversion():
    # Ornstein-Uhlenbeck: Delta y_t = alpha + lambda * y_{t-1} + eps
    # half_life = -ln(2) / lambda
    # For lambda = -0.05, half_life = -0.69315 / -0.05 ≈ 13.86 bars
    import random
    rng = random.Random(42)
    series = [100.0]
    for _ in range(500):
        prev = series[-1]
        noise = rng.gauss(0.0, 0.5)
        # AR(1) with phi = 0.95 -> Delta y = -0.05 * (y - 100) + noise
        series.append(prev - 0.05 * (prev - 100.0) + noise)
    hl = compute_half_life(series)
    assert 8.0 < hl < 20.0

def test_hurst_exponent():
    # Strong trend: H > 0.5
    trending = [100.0 + (i * 2.0) for i in range(250)]
    h = compute_hurst_exponent(trending)
    assert h > 0.5

def test_correlation_matrix():
    # Two identical series -> rho = 1.0
    s1 = [float(i) for i in range(50)]
    s2 = [float(i * 2) for i in range(50)]
    matrix = compute_correlation_matrix({"A": s1, "B": s2})
    assert pytest.approx(matrix[("A", "B")], 1e-4) == 1.0
    assert pytest.approx(matrix[("A", "A")], 1e-4) == 1.0

def test_high_vol_regime_switch():
    # sigma_20 = 0.60, sigma_252 = 0.35 -> ratio = 1.714 > 1.5 -> True
    assert is_high_vol_regime(short_vol=0.60, long_vol=0.35, threshold=1.5) is True
    assert is_high_vol_regime(short_vol=0.30, long_vol=0.35, threshold=1.5) is False
