import math
import pytest
import numpy as np
from core.quant.levels.level2_stats import (
    compute_standard_error,
    compute_sharpe_t_stat,
    compute_ols_regression,
    compute_univariate_hedge_ratio,
    compute_correlation,
    compute_r_squared,
    compute_family_wise_error_rate,
    bonferroni_correction,
    benjamini_hochberg_fdr,
)

def test_standard_error():
    # SE = sigma / sqrt(n)
    # sigma = 2.0, n = 100 -> SE = 2.0 / 10 = 0.2
    se = compute_standard_error(2.0, n=100)
    assert pytest.approx(se, 1e-6) == 0.2

    # From sample data: [1, 2, 3, 4, 5]
    # mean = 3, sample var = 10 / 4 = 2.5, std = sqrt(2.5) ≈ 1.5811388
    # SE = std / sqrt(5) ≈ 0.70710678
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    se_data = compute_standard_error(data)
    assert pytest.approx(se_data, 1e-4) == math.sqrt(2.5 / 5.0)

    # Edge cases
    assert compute_standard_error([], n=0) == 0.0
    assert compute_standard_error([1.0]) == 0.0
    assert compute_standard_error(2.0, n=1) == 0.0
    assert compute_standard_error(2.0, n=0) == 0.0

def test_sharpe_t_stat():
    # t = SR * sqrt(years)
    # Annualized SR = 2.0 over 4 years -> t = 2.0 * 2.0 = 4.0
    t = compute_sharpe_t_stat(sharpe=2.0, years=4.0)
    assert pytest.approx(t, 1e-5) == 4.0

    # With n_samples: SR = 0.1 over 100 bars -> t = 0.1 * 10 = 1.0
    t_samples = compute_sharpe_t_stat(sharpe=0.1, n_samples=100)
    assert pytest.approx(t_samples, 1e-5) == 1.0

    # From return series
    returns = [0.01, 0.02, 0.01, 0.03, -0.01, 0.02]
    # Test that valid float is returned
    t_ret = compute_sharpe_t_stat(returns=returns)
    assert isinstance(t_ret, float)
    assert t_ret > 0.0

    # Degenerate returns (zero variance)
    assert compute_sharpe_t_stat(returns=[0.01, 0.01, 0.01]) == 0.0
    assert compute_sharpe_t_stat(sharpe=1.0, years=0.0) == 0.0

def test_ols_regression():
    # y = 2 * x + 1 + noise
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [3.0, 5.0, 7.0, 9.0, 11.0]  # exact line: beta=2.0, alpha=1.0

    res = compute_ols_regression(x, y, fit_intercept=True)
    assert pytest.approx(res["beta"], 1e-5) == 2.0
    assert pytest.approx(res["alpha"], 1e-5) == 1.0
    assert pytest.approx(res["r_squared"], 1e-5) == 1.0
    assert pytest.approx(res["residual_variance"], 1e-5) == 0.0

    # Univariate hedge ratio Cov(x, y) / Var(x)
    hr = compute_univariate_hedge_ratio(x, y)
    assert pytest.approx(hr, 1e-5) == 2.0

    # Multivariate regression
    X_mat = [[1.0, 2.0], [2.0, 1.0], [3.0, 4.0], [4.0, 3.0], [5.0, 5.0]]
    # y = 2*x1 + 3*x2
    y_multi = [2*r[0] + 3*r[1] for r in X_mat]
    res_multi = compute_ols_regression(X_mat, y_multi, fit_intercept=False)
    assert pytest.approx(res_multi["beta"][0], 1e-4) == 2.0
    assert pytest.approx(res_multi["beta"][1], 1e-4) == 3.0

def test_correlation_and_r_squared():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr = compute_correlation(x, y)
    assert pytest.approx(corr, 1e-5) == 1.0

    # Negative correlation
    y_neg = [10.0, 8.0, 6.0, 4.0, 2.0]
    assert pytest.approx(compute_correlation(x, y_neg), 1e-5) == -1.0

    # R^2
    r2 = compute_r_squared(y_true=y, y_pred=y)
    assert pytest.approx(r2, 1e-5) == 1.0

    # Zero variance inputs
    assert compute_correlation([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) == 0.0

def test_multiple_testing():
    # P(>= 1 false win) = 1 - (1 - alpha)^N
    # alpha = 0.05, N = 20 trials -> 1 - 0.95^20 ≈ 0.6415 (64.2% chance of false discovery!)
    fwer = compute_family_wise_error_rate(alpha=0.05, n_trials=20)
    assert pytest.approx(fwer, 1e-4) == 1.0 - (0.95 ** 20)

    # Bonferroni: alpha / N
    bonf = bonferroni_correction(alpha=0.05, n_trials=20)
    assert pytest.approx(bonf, 1e-6) == 0.05 / 20

    # Benjamini-Hochberg FDR control
    p_vals = [0.001, 0.008, 0.03, 0.045, 0.15, 0.60]
    # With FDR = 0.05, significant tests are flagged
    rejected = benjamini_hochberg_fdr(p_vals, fdr=0.05)
    assert rejected[0] is True  # 0.001 should be significant
    assert rejected[-1] is False  # 0.60 should not be significant
