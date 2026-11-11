"""Level 3: Linear Algebra Engine (Formulas 3.1 - 3.5).

Formulas:
3.1 Covariance Matrix: Sigma_{ij} = Cov(X_i, X_j); Positive semi-definite check and repair
3.2 Portfolio Variance: sigma_p^2 = w^T Sigma w; sigma_p = sqrt(w^T Sigma w)
3.3 Eigenvalues & PCA: Sigma v_i = lambda_i v_i; Variance explained = lambda_i / sum(lambda_j)
3.4 Matrix Conditioning: kappa(Sigma) = lambda_max / lambda_min; safe inverse via pinv
3.5 Ledoit-Wolf Shrinkage: Sigma^* = delta * F + (1 - delta) * S
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence, Union
import numpy as np

try:
    from sklearn.covariance import ledoit_wolf as sk_ledoit_wolf
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


def compute_covariance_matrix(
    returns_matrix: Sequence[Sequence[float]] | np.ndarray,
    ddof: int = 1,
) -> np.ndarray:
    """Calculate sample covariance matrix Sigma with positive semi-definite safety.

    Formula 3.1:
        Sigma_{ij} = (1 / (N - ddof)) * sum (X_{ti} - mean(X_i)) * (X_{tj} - mean(X_j))

    Args:
        returns_matrix: 2D array-like of shape (n_samples, n_assets).
        ddof: Degrees of freedom adjustment (default 1 for sample covariance).

    Returns:
        Symmetric covariance matrix of shape (n_assets, n_assets).
    """
    arr = np.asarray(returns_matrix, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D returns array (n_samples, n_assets), got shape {arr.shape}")

    n_samples, n_assets = arr.shape
    if n_samples <= ddof:
        return np.zeros((n_assets, n_assets), dtype=float)

    # np.cov expects (n_features, n_samples) by default, so rowvar=False
    cov = np.cov(arr, rowvar=False, ddof=ddof)
    if cov.ndim == 0:
        return np.array([[float(cov)]], dtype=float)
    elif cov.ndim == 1:
        return cov.reshape(1, 1)

    # Ensure exact symmetry
    cov = 0.5 * (cov + cov.T)
    return cov


def is_positive_semi_definite(
    matrix: np.ndarray | Sequence[Sequence[float]],
    tol: float = 1e-8,
) -> bool:
    """Check whether a symmetric matrix is Positive Semi-Definite (all eigenvalues >= -tol).

    Formula 3.1.
    """
    mat = np.asarray(matrix, dtype=float)
    if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
        return False

    eigenvalues = np.linalg.eigvalsh(0.5 * (mat + mat.T))
    return bool(np.all(eigenvalues >= -tol))


def ensure_positive_semi_definite(
    matrix: np.ndarray | Sequence[Sequence[float]],
    epsilon: float = 1e-8,
) -> np.ndarray:
    """Project / repair a matrix to the nearest Positive Semi-Definite cone.

    Clips negative eigenvalues to epsilon and reconstructs V * diag(max(lambda, eps)) * V^T.

    Formula 3.1.
    """
    mat = np.asarray(matrix, dtype=float)
    sym = 0.5 * (mat + mat.T)
    eigenvalues, eigenvectors = np.linalg.eigh(sym)

    # Floor negative eigenvalues to epsilon
    clipped_eigenvalues = np.maximum(eigenvalues, epsilon)
    repaired = eigenvectors @ np.diag(clipped_eigenvalues) @ eigenvectors.T
    return 0.5 * (repaired + repaired.T)


def compute_portfolio_variance(
    weights: Sequence[float] | np.ndarray,
    cov_matrix: Sequence[Sequence[float]] | np.ndarray,
) -> float:
    """Calculate quadratic portfolio variance: sigma_p^2 = w^T Sigma w.

    Formula 3.2.

    Args:
        weights: Portfolio asset weights vector w.
        cov_matrix: Covariance matrix Sigma of shape (n_assets, n_assets).

    Returns:
        Portfolio variance (>= 0.0).
    """
    w = np.asarray(weights, dtype=float).flatten()
    sigma = np.asarray(cov_matrix, dtype=float)

    if sigma.ndim != 2 or sigma.shape[0] != sigma.shape[1]:
        raise ValueError(f"Covariance matrix must be square 2D, got shape {sigma.shape}")
    if len(w) != sigma.shape[0]:
        raise ValueError(f"Dimension mismatch: weights length {len(w)} vs cov shape {sigma.shape}")

    var_p = float(w @ sigma @ w)
    return max(0.0, var_p)


def compute_portfolio_volatility(
    weights: Sequence[float] | np.ndarray,
    cov_matrix: Sequence[Sequence[float]] | np.ndarray,
) -> float:
    """Calculate portfolio standard deviation / volatility: sigma_p = sqrt(w^T Sigma w).

    Formula 3.2.
    """
    var_p = compute_portfolio_variance(weights, cov_matrix)
    return math.sqrt(var_p)


def compute_pca_factors(
    returns_matrix: Sequence[Sequence[float]] | np.ndarray,
    n_components: Optional[int] = None,
) -> dict[str, Any]:
    """Extract principal variance components and market drivers via Eigen-decomposition.

    Formula 3.3:
        Sigma v_i = lambda_i v_i
        Variance explained = lambda_i / sum(lambda_j)

    Args:
        returns_matrix: 2D returns array of shape (n_samples, n_assets) or precomputed covariance matrix.
        n_components: Number of top principal components to retain (default: all).

    Returns:
        dict containing:
            - eigenvalues: Array of sorted eigenvalues (descending).
            - eigenvectors: Matrix of principal components (columns).
            - explained_variance_ratio: Proportion of variance explained by retained components.
            - all_explained_variance_ratio: Proportion of variance for all components.
            - cumulative_variance: Cumulative variance explained by retained components.
    """
    arr = np.asarray(returns_matrix, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {arr.shape}")

    if arr.shape[0] == arr.shape[1] and np.allclose(arr, arr.T, atol=1e-5):
        cov = arr
    else:
        cov = compute_covariance_matrix(arr)

    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # Sort descending
    sort_idx = np.argsort(eigenvalues)[::-1]
    sorted_eigenvalues = np.maximum(0.0, eigenvalues[sort_idx])
    sorted_eigenvectors = eigenvectors[:, sort_idx]

    total_var = float(np.sum(sorted_eigenvalues))
    if total_var <= 1e-15:
        all_ratios = np.zeros_like(sorted_eigenvalues)
    else:
        all_ratios = sorted_eigenvalues / total_var

    k = len(sorted_eigenvalues) if n_components is None else min(n_components, len(sorted_eigenvalues))

    retained_eigenvalues = sorted_eigenvalues[:k]
    retained_eigenvectors = sorted_eigenvectors[:, :k]
    retained_ratios = all_ratios[:k]
    cumulative = np.cumsum(retained_ratios)

    return {
        "eigenvalues": retained_eigenvalues,
        "eigenvectors": retained_eigenvectors,
        "explained_variance_ratio": retained_ratios,
        "all_explained_variance_ratio": all_ratios,
        "cumulative_variance": cumulative,
    }


def compute_condition_number(
    matrix: Sequence[Sequence[float]] | np.ndarray,
) -> float:
    """Calculate the condition number of a matrix: kappa(Sigma) = lambda_max / lambda_min.

    Formula 3.4.
    """
    mat = np.asarray(matrix, dtype=float)
    if mat.size == 0:
        return 1.0

    cond = float(np.linalg.cond(mat))
    return cond


def is_well_conditioned(
    matrix: Sequence[Sequence[float]] | np.ndarray,
    max_condition: float = 1e4,
) -> bool:
    """Check if matrix condition number is below numerical explosion threshold.

    Formula 3.4.
    """
    cond = compute_condition_number(matrix)
    return bool(np.isfinite(cond) and cond <= max_condition)


def safe_matrix_inverse(
    matrix: Sequence[Sequence[float]] | np.ndarray,
    rcond: float = 1e-10,
) -> np.ndarray:
    """Safely invert a matrix using regular inverse or Moore-Penrose pseudo-inverse fallback.

    Formula 3.4.
    """
    mat = np.asarray(matrix, dtype=float)
    if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
        raise ValueError(f"Matrix must be square, got shape {mat.shape}")

    try:
        cond = float(np.linalg.cond(mat))
        if np.isfinite(cond) and cond < 1e10:
            return np.linalg.inv(mat)
    except (np.linalg.LinAlgError, ValueError):
        pass

    # Robust pseudo-inverse fallback
    return np.linalg.pinv(mat, rcond=rcond)


def ledoit_wolf_shrinkage(
    returns_or_cov: np.ndarray | Sequence[Sequence[float]],
    shrinkage_delta: Optional[float] = None,
    target: str = "constant_correlation",
) -> tuple[np.ndarray, float]:
    """Shrink sample covariance matrix towards structured target: Sigma^* = delta * F + (1 - delta) * S.

    Formula 3.5.

    Args:
        returns_or_cov: Returns matrix of shape (n_samples, n_features) or covariance matrix.
        shrinkage_delta: Optional manual shrinkage intensity delta in [0, 1]. If None, estimated optimally.
        target: Target type ('constant_correlation' or 'identity').

    Returns:
        tuple (shrunk_cov_matrix, shrinkage_delta).
    """
    arr = np.asarray(returns_or_cov, dtype=float)

    # Check if input is a sample return matrix or covariance matrix
    is_returns = not (arr.ndim == 2 and arr.shape[0] == arr.shape[1] and np.allclose(arr, arr.T, atol=1e-5))

    if shrinkage_delta is None and is_returns and _HAS_SKLEARN:
        # Use scikit-learn analytical Ledoit-Wolf
        shrunk_cov, delta = sk_ledoit_wolf(arr)
        return shrunk_cov, float(delta)

    # Compute sample covariance S
    if is_returns:
        S = compute_covariance_matrix(arr)
        X = arr
    else:
        S = arr
        X = None

    p = S.shape[0]

    # Target matrix F
    if target == "identity":
        mu = float(np.trace(S) / p)
        F = mu * np.eye(p)
    else:
        # Constant correlation target
        vars_diag = np.diag(S)
        stds = np.sqrt(np.maximum(1e-15, vars_diag))
        corr = S / np.outer(stds, stds)
        # Average off-diagonal correlation
        r_bar = float((np.sum(corr) - p) / max(1, p * (p - 1)))
        F_corr = np.full((p, p), r_bar)
        np.fill_diagonal(F_corr, 1.0)
        F = np.outer(stds, stds) * F_corr

    # If delta is explicitly given
    if shrinkage_delta is not None:
        delta = max(0.0, min(1.0, float(shrinkage_delta)))
    else:
        # Analytical approximation for delta if returns matrix is available
        if X is not None and X.shape[0] > 1:
            n = X.shape[0]
            X_c = X - np.mean(X, axis=0)
            # Estimate sum of asymptotic variances pi_hat
            pi_mat = np.zeros((p, p))
            for t in range(n):
                outer_t = np.outer(X_c[t], X_c[t]) - S
                pi_mat += outer_t ** 2
            pi_hat = float(np.sum(pi_mat) / n)

            # Estimate gamma_hat = ||S - F||_F^2
            gamma_hat = float(np.sum((S - F) ** 2))

            kappa = pi_hat / max(1e-15, gamma_hat)
            delta = max(0.0, min(1.0, kappa / n))
        else:
            delta = 0.2

    shrunk_cov = delta * F + (1.0 - delta) * S
    shrunk_cov = 0.5 * (shrunk_cov + shrunk_cov.T)
    return shrunk_cov, delta
