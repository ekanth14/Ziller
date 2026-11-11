"""Level 2: Statistics Engine (Formulas 2.1 - 2.5).

Formulas:
2.1 Standard Error: SE = sigma / sqrt(n)
2.2 Sharpe t-stat: t = SR * sqrt(years) or t = (mean_r - rf) / (s / sqrt(n))
2.3 OLS Regression: beta = (X^T X)^(-1) X^T y; univariate hedge ratio beta = Cov(x, y) / Var(x)
2.4 Correlation & R^2: rho = Cov(X, Y) / (sigma_X * sigma_Y); R^2 = 1 - SS_res / SS_tot
2.5 Multiple Testing: FWER = 1 - (1 - alpha)^N; Bonferroni alpha / N; Benjamini-Hochberg FDR
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence, Union
import numpy as np


def compute_standard_error(
    data_or_sigma: Union[float, Sequence[float]],
    n: Optional[int] = None,
) -> float:
    """Calculate the Standard Error of the mean: SE = sigma / sqrt(n).

    Formula 2.1:
        SE = sigma / sqrt(n)

    Args:
        data_or_sigma: Either a sample sequence of numbers or a precomputed standard deviation.
        n: Sample size (required if data_or_sigma is a float standard deviation).

    Returns:
        Standard error (float >= 0.0).
    """
    if isinstance(data_or_sigma, (int, float)):
        sigma = float(data_or_sigma)
        if n is None or n <= 1:
            return 0.0
        return max(0.0, sigma / math.sqrt(n))

    data = list(data_or_sigma)
    count = len(data)
    if count <= 1:
        return 0.0

    mean_val = sum(data) / count
    var = sum((x - mean_val) ** 2 for x in data) / (count - 1)
    if var <= 1e-15:
        return 0.0
    return math.sqrt(var / count)


def compute_sharpe_t_stat(
    sharpe: Optional[float] = None,
    n_samples: Optional[int] = None,
    years: Optional[float] = None,
    returns: Optional[Sequence[float]] = None,
    risk_free_rate: float = 0.0,
) -> float:
    """Calculate t-statistic for Sharpe ratio significance against null hypothesis (SR = 0).

    Formula 2.2:
        t = SR * sqrt(years) or t = SR * sqrt(N)

    Args:
        sharpe: Point estimate of annualized or per-period Sharpe ratio.
        n_samples: Number of sample observation periods.
        years: Backtest duration in years.
        returns: Raw return series (if Sharpe is not precomputed).
        risk_free_rate: Per-period risk-free rate when returns are supplied.

    Returns:
        t-statistic (float).
    """
    if returns is not None:
        ret_list = list(returns)
        if len(ret_list) <= 1:
            return 0.0
        excess_returns = [r - risk_free_rate for r in ret_list]
        n = len(excess_returns)
        mean_ret = sum(excess_returns) / n
        var = sum((r - mean_ret) ** 2 for r in excess_returns) / (n - 1)
        if var <= 1e-15:
            return 0.0
        se = math.sqrt(var / n)
        return float(mean_ret / se)

    if sharpe is not None:
        if years is not None and years > 0.0:
            return float(sharpe * math.sqrt(years))
        if n_samples is not None and n_samples > 1:
            return float(sharpe * math.sqrt(n_samples))

    return 0.0


def compute_univariate_hedge_ratio(
    x: Sequence[float],
    y: Sequence[float],
) -> float:
    """Calculate univariate OLS hedge ratio: beta = Cov(x, y) / Var(x).

    Formula 2.3.
    """
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / (n - 1)
    var_x = sum((xi - mean_x) ** 2 for xi in x) / (n - 1)

    if var_x <= 1e-15:
        return 0.0
    return float(cov_xy / var_x)


def compute_ols_regression(
    x: Sequence[float] | Sequence[Sequence[float]] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    fit_intercept: bool = True,
) -> dict[str, Any]:
    """Calculate Ordinary Least Squares (OLS) regression: beta = (X^T X)^(-1) X^T y.

    Formula 2.3.

    Args:
        x: 1D array/sequence of independent variable or 2D matrix of shape (n_samples, n_features).
        y: Dependent variable array of shape (n_samples,).
        fit_intercept: If True, adds an intercept/alpha term.

    Returns:
        dict containing:
            - beta: Estimated slope(s) (float for univariate, list[float] for multivariate).
            - alpha: Estimated intercept.
            - residuals: list of residual errors (y - y_hat).
            - residual_variance: Unbiased estimate of residual variance sigma^2_eps.
            - r_squared: Coefficient of determination R^2.
    """
    y_arr = np.asarray(y, dtype=float).flatten()
    n = len(y_arr)
    if n < 2:
        raise ValueError(f"Need at least 2 samples for OLS regression, got {n}")

    x_arr = np.asarray(x, dtype=float)
    is_univariate = (x_arr.ndim == 1) or (x_arr.ndim == 2 and x_arr.shape[1] == 1)

    if is_univariate:
        x_flat = x_arr.flatten()
        if len(x_flat) != n:
            raise ValueError(f"x and y length mismatch: {len(x_flat)} vs {n}")
        X_mat = x_flat.reshape(-1, 1)
    else:
        if x_arr.shape[0] != n:
            raise ValueError(f"X rows and y length mismatch: {x_arr.shape[0]} vs {n}")
        X_mat = x_arr

    if fit_intercept:
        ones = np.ones((n, 1), dtype=float)
        X_design = np.hstack([ones, X_mat])
    else:
        X_design = X_mat

    # Solve normal equations: (X^T X) beta = X^T y using robust least-squares
    beta_all, residuals_sum, rank, s = np.linalg.lstsq(X_design, y_arr, rcond=1e-10)

    if fit_intercept:
        alpha = float(beta_all[0])
        beta = float(beta_all[1]) if is_univariate else beta_all[1:].tolist()
    else:
        alpha = 0.0
        beta = float(beta_all[0]) if is_univariate else beta_all.tolist()

    y_pred = X_design @ beta_all
    residuals = y_arr - y_pred

    k = X_design.shape[1]
    df_resid = max(1, n - k)
    residual_variance = float(np.sum(residuals ** 2) / df_resid)

    ss_tot = float(np.sum((y_arr - np.mean(y_arr)) ** 2))
    ss_res = float(np.sum(residuals ** 2))

    if ss_tot <= 1e-15:
        r_squared = 1.0 if ss_res <= 1e-15 else 0.0
    else:
        r_squared = max(0.0, min(1.0, float(1.0 - (ss_res / ss_tot))))

    return {
        "beta": beta,
        "alpha": alpha,
        "residuals": residuals.tolist(),
        "residual_variance": residual_variance,
        "r_squared": r_squared,
    }


def compute_correlation(
    x: Sequence[float],
    y: Sequence[float],
) -> float:
    """Calculate Pearson correlation coefficient rho = Cov(X, Y) / (sigma_X * sigma_Y).

    Formula 2.4.
    """
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / (n - 1)
    var_x = sum((xi - mean_x) ** 2 for xi in x) / (n - 1)
    var_y = sum((yi - mean_y) ** 2 for yi in y) / (n - 1)

    denom = math.sqrt(var_x * var_y)
    if denom <= 1e-15:
        return 0.0

    corr = cov_xy / denom
    return max(-1.0, min(1.0, float(corr)))


def compute_r_squared(
    y_true: Sequence[float],
    y_pred: Sequence[float],
) -> float:
    """Calculate coefficient of determination R^2 = 1 - SS_res / SS_tot.

    Formula 2.4.
    """
    if len(y_true) != len(y_pred) or len(y_true) < 2:
        return 0.0

    y_arr = np.asarray(y_true, dtype=float)
    pred_arr = np.asarray(y_pred, dtype=float)

    ss_res = float(np.sum((y_arr - pred_arr) ** 2))
    ss_tot = float(np.sum((y_arr - np.mean(y_arr)) ** 2))

    if ss_tot <= 1e-15:
        return 1.0 if ss_res <= 1e-15 else 0.0

    return max(0.0, min(1.0, float(1.0 - (ss_res / ss_tot))))


def compute_family_wise_error_rate(
    alpha: float,
    n_trials: int,
) -> float:
    """Calculate Family-Wise Error Rate (FWER) across N independent trials.

    Formula 2.5:
        P(>= 1 false discovery) = 1 - (1 - alpha)^N

    Args:
        alpha: Single-test significance level (e.g. 0.05).
        n_trials: Number of hypotheses/backtest configurations tested.

    Returns:
        Probability of at least 1 false positive in [0, 1].
    """
    if n_trials <= 0:
        return 0.0
    if not (0.0 <= alpha <= 1.0):
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")

    prob = 1.0 - ((1.0 - alpha) ** n_trials)
    return max(0.0, min(1.0, float(prob)))


def bonferroni_correction(
    alpha: float,
    n_trials: int,
) -> float:
    """Calculate Bonferroni adjusted significance threshold: alpha_adj = alpha / N.

    Formula 2.5.
    """
    if n_trials <= 0:
        return alpha
    return float(alpha / n_trials)


def benjamini_hochberg_fdr(
    p_values: Sequence[float],
    fdr: float = 0.05,
) -> list[bool]:
    """Control False Discovery Rate (FDR) using the Benjamini-Hochberg procedure.

    Formula 2.5:
        Ranks p-values p_(1) <= ... <= p_(m).
        Finds largest k such that p_(k) <= (k / m) * FDR.
        Rejects all hypotheses 1 <= i <= k.

    Args:
        p_values: List of unadjusted p-values from multiple backtests/signals.
        fdr: False Discovery Rate ceiling (default 0.05).

    Returns:
        List of booleans corresponding to each input p-value: True if significant.
    """
    m = len(p_values)
    if m == 0:
        return []

    # Pair with original indices
    indexed_p = sorted(enumerate(p_values), key=lambda x: x[1])

    # Find largest k such that p_(k) <= (k / m) * fdr
    max_k = -1
    for rank_idx, (orig_idx, p_val) in enumerate(indexed_p, start=1):
        threshold = (rank_idx / m) * fdr
        if p_val <= threshold:
            max_k = rank_idx

    rejected = [False] * m
    if max_k > 0:
        for i in range(max_k):
            orig_idx = indexed_p[i][0]
            rejected[orig_idx] = True

    return rejected
