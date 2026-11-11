"""Level 5: Time Series Analysis Engine (Formulas 5.1 - 5.5).

Formulas:
5.1 Log Returns & Annualized Volatility: r_t = ln(P_t / P_{t-1}), sigma_year = sigma_bar * sqrt(N)
5.2 Autocorrelation: rho_k = Cov(r_t, r_{t-k}) / sigma^2
5.3 Stationarity (ADF Test): Delta y_t = alpha + gamma * y_{t-1} + eps (crit -2.86 at 5%)
5.4 Cointegration & Half-Life: eps_t = y_t - beta * x_t, tau_half = -ln(2) / lambda (OU)
5.5 GARCH(1,1) Volatility: sigma_t^2 = omega + alpha * eps_{t-1}^2 + beta * sigma_{t-1}^2
"""

from __future__ import annotations

import math
from typing import Sequence, Union
import numpy as np


# ---------------------------------------------------------------------------
# Formula 5.1: Log Returns & Annualized Volatility
# ---------------------------------------------------------------------------

def compute_log_returns(prices: Sequence[float]) -> list[float]:
    """Calculate log returns r_t = ln(P_t / P_{t-1}).

    Guarantees:
    - Multi-period additive property: sum(r_t) == ln(P_T / P_0)
    - Rejects non-positive prices with ValueError.
    - Zero lookahead: r_t depends exclusively on P_t and P_{t-1}.
    """
    if len(prices) < 2:
        return []

    returns: list[float] = []
    for i in range(1, len(prices)):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        if p_prev <= 0.0 or p_curr <= 0.0:
            raise ValueError(f"Prices must be strictly positive: {p_prev=}, {p_curr=}")
        returns.append(math.log(p_curr / p_prev))
    return returns


def compute_annualized_volatility(
    returns_or_vol: Union[float, Sequence[float]],
    bars_per_year: float = 365.0,
) -> float:
    """Annualize volatility: sigma_year = sigma_bar * sqrt(bars_per_year).

    Accepts either a scalar bar volatility (float) or a sequence of returns.
    For 24/7/365 crypto markets, default bars_per_year is 365 (or 365*24 for 1h bars).
    For TradFi, use 252.
    """
    if isinstance(returns_or_vol, (int, float)):
        return float(returns_or_vol) * math.sqrt(bars_per_year)

    returns = list(returns_or_vol)
    n = len(returns)
    if n < 2:
        return 0.0

    mean_r = sum(returns) / n
    var = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    bar_vol = math.sqrt(var)
    return bar_vol * math.sqrt(bars_per_year)


# ---------------------------------------------------------------------------
# Formula 5.2: Autocorrelation
# ---------------------------------------------------------------------------

def compute_autocorrelation(series: Sequence[float], lag: int = 1) -> float:
    """Calculate sample autocorrelation at lag k: rho_k = Cov(r_t, r_{t-k}) / sigma^2.

    Returns float in [-1.0, 1.0].
    rho_1 > 0 indicates momentum; rho_1 < 0 indicates mean reversion.
    """
    n = len(series)
    if lag < 1 or n <= lag + 1:
        return 0.0

    mean_val = sum(series) / n
    denom = sum((x - mean_val) ** 2 for x in series)
    if denom <= 1e-12:
        return 0.0

    nom = sum((series[t] - mean_val) * (series[t - lag] - mean_val) for t in range(lag, n))
    autocorr = nom / denom
    return max(-1.0, min(1.0, autocorr))


def classify_autocorrelation_regime(autocorr: float, threshold: float = 0.05) -> str:
    """Classify regime based on lag-1 autocorrelation: 'momentum', 'mean_reverting', or 'neutral'."""
    if autocorr > threshold:
        return "momentum"
    elif autocorr < -threshold:
        return "mean_reverting"
    return "neutral"


# ---------------------------------------------------------------------------
# Formula 5.3: Stationarity (ADF Test)
# ---------------------------------------------------------------------------

def compute_adf_stationarity(
    series: Sequence[float],
    critical_value: float = -2.86,
) -> tuple[float, bool]:
    """Perform Augmented Dickey-Fuller stationarity test: Delta y_t = alpha + gamma * y_{t-1} + eps.

    Null hypothesis H0: gamma = 0 (unit root / non-stationary).
    Reject H0 when gamma < 0 and t_stat < critical_value (typically -2.86 at 5% significance level).

    Returns:
        (t_stat, is_stationary)
    """
    n = len(series)
    if n < 10:
        return 0.0, False

    y_lag = [series[i - 1] for i in range(1, n)]
    delta_y = [series[i] - series[i - 1] for i in range(1, n)]
    m = len(y_lag)

    mean_x = sum(y_lag) / m
    mean_y = sum(delta_y) / m

    ss_xx = sum((x - mean_x) ** 2 for x in y_lag)
    ss_xy = sum((y_lag[i] - mean_x) * (delta_y[i] - mean_y) for i in range(m))

    if ss_xx <= 1e-12:
        return 0.0, False

    gamma = ss_xy / ss_xx
    alpha = mean_y - gamma * mean_x

    residuals = [delta_y[i] - (alpha + gamma * y_lag[i]) for i in range(m)]
    sse = sum(e ** 2 for e in residuals)
    var_eps = sse / max(1, m - 2)
    se_gamma = math.sqrt(var_eps / ss_xx)

    if se_gamma <= 1e-12:
        return 0.0, False

    t_stat = gamma / se_gamma
    is_stationary = (gamma < 0.0) and (t_stat < critical_value)
    return t_stat, bool(is_stationary)


# Alias for backwards compatibility with earlier stage modules
compute_adf_test = compute_adf_stationarity


# ---------------------------------------------------------------------------
# Formula 5.4: Cointegration & Half-Life
# ---------------------------------------------------------------------------

def compute_cointegration_hedge_ratio(
    series_y: Sequence[float],
    series_x: Sequence[float],
) -> tuple[float, float, list[float]]:
    """Estimate cointegrating relationship: y_t = alpha + beta * x_t + eps_t.

    Returns:
        (beta, alpha, spread)
    """
    n = min(len(series_y), len(series_x))
    if n < 3:
        return 0.0, 0.0, []

    y = list(series_y[-n:])
    x = list(series_x[-n:])

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    ss_xx = sum((xi - mean_x) ** 2 for xi in x)
    ss_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))

    if ss_xx <= 1e-12:
        return 0.0, mean_y, [yi - mean_y for yi in y]

    beta = ss_xy / ss_xx
    alpha = mean_y - beta * mean_x
    spread = [y[i] - (alpha + beta * x[i]) for i in range(n)]

    return beta, alpha, spread


def compute_half_life(series: Sequence[float], dt: float = 1.0) -> float:
    """Calculate Ornstein-Uhlenbeck mean-reversion half-life: tau_half = -ln(2) / lambda.

    Estimated from regression Delta y_t = alpha + lambda * y_{t-1} * dt + eps.
    If lambda >= 0 (divergent or random walk), returns float('inf').
    """
    n = len(series)
    if n < 5:
        return float("inf")

    y_lag = [series[i - 1] for i in range(1, n)]
    delta_y = [series[i] - series[i - 1] for i in range(1, n)]
    m = len(y_lag)

    mean_x = sum(y_lag) / m
    mean_y = sum(delta_y) / m

    ss_xx = sum((x - mean_x) ** 2 for x in y_lag)
    ss_xy = sum((y_lag[i] - mean_x) * (delta_y[i] - mean_y) for i in range(m))

    if ss_xx <= 1e-12:
        return float("inf")

    lambda_param = (ss_xy / ss_xx) / dt
    if lambda_param >= 0.0:
        return float("inf")

    return -math.log(2.0) / lambda_param


# ---------------------------------------------------------------------------
# Formula 5.5: GARCH(1,1) Volatility
# ---------------------------------------------------------------------------

def compute_garch11_filter(
    returns: Sequence[float],
    omega: float,
    alpha: float,
    beta: float,
    initial_sigma2: float | None = None,
) -> list[float]:
    """Filter return sequence using GARCH(1,1): sigma_t^2 = omega + alpha * eps_{t-1}^2 + beta * sigma_{t-1}^2.

    Returns the series of conditional variances [sigma_0^2, sigma_1^2, ..., sigma_{T-1}^2].
    """
    n = len(returns)
    if n == 0:
        return []

    # Persistence check
    persistence = alpha + beta
    if persistence >= 1.0:
        uncond_var = (sum(r ** 2 for r in returns) / n) if n > 0 else 0.0001
    else:
        uncond_var = omega / (1.0 - persistence)

    current_var = initial_sigma2 if (initial_sigma2 is not None and initial_sigma2 > 0) else uncond_var
    variances: list[float] = [current_var]

    for t in range(1, n):
        eps_prev = returns[t - 1]
        current_var = omega + alpha * (eps_prev ** 2) + beta * current_var
        variances.append(current_var)

    return variances


def forecast_garch11_next(
    last_sigma2: float,
    last_return: float,
    omega: float,
    alpha: float,
    beta: float,
) -> float:
    """Compute one-step-ahead GARCH(1,1) variance forecast."""
    return omega + alpha * (last_return ** 2) + beta * last_sigma2


def estimate_garch11_parameters(returns: Sequence[float]) -> dict[str, float]:
    """Fit GARCH(1,1) model parameters (omega, alpha, beta) to returns via Maximum Likelihood.

    Returns dictionary with:
    - omega: baseline constant variance
    - alpha: ARCH innovation coefficient
    - beta: GARCH persistence coefficient
    - persistence: alpha + beta (< 1 for stationarity)
    - long_run_vol: sqrt(omega / (1 - alpha - beta))
    """
    ret_arr = np.array(returns, dtype=float)
    n = len(ret_arr)
    if n < 10:
        sample_var = float(np.var(ret_arr, ddof=1)) if n > 1 else 0.0001
        return {
            "omega": 0.05 * sample_var,
            "alpha": 0.10,
            "beta": 0.85,
            "persistence": 0.95,
            "long_run_vol": math.sqrt(sample_var),
        }

    sample_var = float(np.var(ret_arr, ddof=1))
    if sample_var <= 1e-12:
        sample_var = 1e-6

    from scipy.optimize import minimize

    # Parameterization: [log_omega, logit_alpha, logit_beta] or direct bounds
    def neg_log_likelihood(params: np.ndarray) -> float:
        omega, alpha, beta = params
        if omega <= 1e-8 or alpha < 0.0 or beta < 0.0 or (alpha + beta) >= 0.999:
            return 1e10

        sigma2 = sample_var
        ll = 0.0
        for r in ret_arr:
            sigma2 = omega + alpha * (r ** 2) + beta * sigma2
            if sigma2 <= 1e-12:
                sigma2 = 1e-12
            ll += 0.5 * (math.log(sigma2) + (r ** 2) / sigma2)
        return ll

    init_alpha = 0.10
    init_beta = 0.80
    init_omega = sample_var * (1.0 - init_alpha - init_beta)
    init_params = np.array([init_omega, init_alpha, init_beta])

    bounds = [(1e-8, sample_var * 2.0), (0.01, 0.40), (0.40, 0.95)]
    res = minimize(
        neg_log_likelihood,
        init_params,
        method="L-BFGS-B",
        bounds=bounds,
    )

    if res.success:
        om, al, be = res.x
    else:
        om, al, be = init_omega, init_alpha, init_beta

    pers = al + be
    if pers >= 1.0:
        pers = 0.99
        be = pers - al
    long_run_var = om / max(1e-6, (1.0 - pers))

    return {
        "omega": float(om),
        "alpha": float(al),
        "beta": float(be),
        "persistence": float(pers),
        "long_run_vol": float(math.sqrt(max(0.0, long_run_var))),
    }
