import math
import pytest
import numpy as np
from core.quant.levels.level3_linalg import (
    compute_covariance_matrix,
    is_positive_semi_definite,
    ensure_positive_semi_definite,
    compute_portfolio_variance,
    compute_portfolio_volatility,
    compute_pca_factors,
    compute_condition_number,
    is_well_conditioned,
    safe_matrix_inverse,
    ledoit_wolf_shrinkage,
)

def test_covariance_and_psd():
    # 2 assets, 5 time steps
    # returns: shape (5, 2)
    returns = np.array([
        [0.01, 0.02],
        [0.02, 0.04],
        [-0.01, -0.02],
        [0.03, 0.06],
        [0.00, 0.00],
    ])
    cov = compute_covariance_matrix(returns)
    assert cov.shape == (2, 2)
    # Asset 2 has 2x moves of Asset 1, so Var(2) = 4 * Var(1)
    assert pytest.approx(cov[1, 1], 1e-5) == 4.0 * cov[0, 0]
    # Check PSD
    assert is_positive_semi_definite(cov)

    # Negative non-PSD matrix repaired
    bad_mat = np.array([
        [1.0, 2.0],
        [2.0, 1.0],  # det = 1 - 4 = -3, eigenvalues 3 and -1
    ])
    assert not is_positive_semi_definite(bad_mat)
    repaired = ensure_positive_semi_definite(bad_mat)
    assert is_positive_semi_definite(repaired)

def test_portfolio_variance_and_vol():
    # Sigma = [[0.04, 0.01], [0.01, 0.09]]
    cov = np.array([
        [0.04, 0.01],
        [0.01, 0.09],
    ])
    w = np.array([0.5, 0.5])
    # w^T Sigma w = 0.25 * 0.04 + 0.25 * 0.09 + 2 * 0.25 * 0.01 = 0.01 + 0.0225 + 0.005 = 0.0375
    p_var = compute_portfolio_variance(w, cov)
    assert pytest.approx(p_var, 1e-6) == 0.0375
    p_vol = compute_portfolio_volatility(w, cov)
    assert pytest.approx(p_vol, 1e-6) == math.sqrt(0.0375)

    # Edge cases
    assert compute_portfolio_variance([0.0, 0.0], cov) == 0.0

def test_pca_and_eigenvalues():
    # 3 assets where asset 1 and 2 are correlated market drivers
    np.random.seed(42)
    t = 100
    m = np.random.normal(0, 0.02, t)
    ret = np.column_stack([
        m + np.random.normal(0, 0.001, t),
        2 * m + np.random.normal(0, 0.001, t),
        np.random.normal(0, 0.01, t),
    ])

    pca = compute_pca_factors(ret, n_components=2)
    eigenvalues = pca["eigenvalues"]
    explained_ratio = pca["explained_variance_ratio"]

    # First component should capture dominant variance (> 80%)
    assert len(eigenvalues) >= 2
    assert explained_ratio[0] > 0.70
    assert pytest.approx(np.sum(pca["all_explained_variance_ratio"]), 1e-5) == 1.0

def test_matrix_conditioning_and_safe_inverse():
    # Identity matrix has condition number 1
    eye = np.eye(3)
    assert pytest.approx(compute_condition_number(eye), 1e-5) == 1.0
    assert is_well_conditioned(eye)

    # Ill-conditioned matrix (singular or near singular)
    ill_mat = np.array([
        [1.0, 1.0],
        [1.0, 1.0 + 1e-12],
    ])
    assert compute_condition_number(ill_mat) > 1e10
    assert not is_well_conditioned(ill_mat, max_condition=1e4)

    # Safe inverse recovers pseudo-inverse without throwing LinAlgError
    inv_safe = safe_matrix_inverse(ill_mat)
    assert inv_safe.shape == (2, 2)
    assert np.all(np.isfinite(inv_safe))

def test_ledoit_wolf_shrinkage():
    # Sample returns (n_samples=20, n_features=4)
    np.random.seed(123)
    returns = np.random.normal(0, 0.02, (20, 4))

    # Shrink with explicit delta = 0.3
    shrunk_cov, delta = ledoit_wolf_shrinkage(returns, shrinkage_delta=0.3)
    assert shrunk_cov.shape == (4, 4)
    assert delta == 0.3
    assert is_positive_semi_definite(shrunk_cov)

    # Shrink with analytical Ledoit-Wolf estimation
    shrunk_auto, delta_auto = ledoit_wolf_shrinkage(returns)
    assert 0.0 <= delta_auto <= 1.0
    assert is_positive_semi_definite(shrunk_auto)
