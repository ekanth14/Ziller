"""Stage 3: Statistical Filter Engine (Formulas 3.1 - 3.6).

Formulas:
3.1 t-stat of returns: t = mean / (sigma / sqrt(n))
3.2 ADF test: Delta y_t = alpha + gamma * y_{t-1} + eps_t (crit -2.86 at 5%)
3.3 Half-life: half_life = -ln(2) / lambda (Ornstein-Uhlenbeck)
3.4 Hurst exponent: E[R/S] ~ n^H
3.5 Correlation: rho = cov(x, y) / (sigma_x * sigma_y)
3.6 Regime switch: sigma_20 / sigma_252 > 1.5 -> high-vol regime
"""

import math
from typing import Mapping, Sequence


def compute_tstat_returns(returns: Sequence[float]) -> float:
    """Calculate t-statistic of returns: t = mean / (sigma / sqrt(n)). Below 2, assume luck."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean_r = sum(returns) / n
    var = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    sigma = math.sqrt(var)
    if sigma <= 1e-12:
        return 0.0
    se = sigma / math.sqrt(n)
    return mean_r / se


def compute_adf_test(series: Sequence[float]) -> tuple[float, bool]:
    """Perform Augmented Dickey-Fuller (ADF) stationarity test: Delta y_t = alpha + gamma * y_{t-1} + eps.

    Returns (test_statistic, is_stationary_at_5pct).
    Critical value at 5% is approx -2.86.
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
    # At 5% significance level, critical value for ADF with constant is -2.86
    is_stationary = gamma < 0.0 and t_stat < -2.86
    return t_stat, is_stationary


def compute_half_life(series: Sequence[float]) -> float:
    """Calculate Ornstein-Uhlenbeck mean-reversion half-life: half_life = -ln(2) / lambda.

    From regression Delta y_t = alpha + lambda * y_{t-1} + eps.
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

    lambda_param = ss_xy / ss_xx
    if lambda_param >= 0.0:
        return float("inf")  # Non-mean-reverting or explosive

    return -math.log(2.0) / lambda_param


def compute_hurst_exponent(series: Sequence[float], max_lags: int = 20) -> float:
    """Estimate Hurst exponent H using Rescaled Range (R/S) analysis.

    H < 0.5: mean-reverting, H = 0.5: random walk, H > 0.5: trending.
    """
    n = len(series)
    if n < 50:
        return 0.5

    lags = [lag for lag in range(10, min(n // 2, 100), 5)]
    if len(lags) < 3:
        return 0.5

    log_lags: list[float] = []
    log_rs: list[float] = []

    for lag in lags:
        rs_vals: list[float] = []
        for i in range(0, n - lag + 1, lag):
            sub = series[i : i + lag]
            if len(sub) < lag:
                continue
            mean_sub = sum(sub) / lag
            # Cumulative deviations from mean
            devs = [x - mean_sub for x in sub]
            cum_devs: list[float] = []
            cur = 0.0
            for d in devs:
                cur += d
                cum_devs.append(cur)

            r_val = max(cum_devs) - min(cum_devs)
            var_sub = sum(d ** 2 for d in devs) / lag
            s_val = math.sqrt(var_sub)

            if s_val > 1e-12:
                rs_vals.append(r_val / s_val)

        if rs_vals:
            avg_rs = sum(rs_vals) / len(rs_vals)
            if avg_rs > 0.0:
                log_lags.append(math.log(lag))
                log_rs.append(math.log(avg_rs))

    if len(log_lags) < 2:
        return 0.5

    # Linear regression of log(R/S) against log(lag)
    mean_x = sum(log_lags) / len(log_lags)
    mean_y = sum(log_rs) / len(log_rs)
    ss_xx = sum((x - mean_x) ** 2 for x in log_lags)
    ss_xy = sum((log_lags[i] - mean_x) * (log_rs[i] - mean_y) for i in range(len(log_lags)))

    if ss_xx <= 1e-12:
        return 0.5

    h = ss_xy / ss_xx
    # Bound to reasonable financial range [0.0, 1.0]
    return max(0.0, min(1.0, h))


def compute_correlation_matrix(
    series_dict: Mapping[str, Sequence[float]],
) -> dict[tuple[str, str], float]:
    """Calculate Pearson correlation matrix between all pairs of assets: rho = cov(x,y)/(sigma_x * sigma_y)."""
    keys = list(series_dict.keys())
    result: dict[tuple[str, str], float] = {}

    for i in range(len(keys)):
        for j in range(len(keys)):
            k1 = keys[i]
            k2 = keys[j]
            if k1 == k2:
                result[(k1, k2)] = 1.0
                continue
            s1 = series_dict[k1]
            s2 = series_dict[k2]
            min_len = min(len(s1), len(s2))
            if min_len < 2:
                result[(k1, k2)] = 0.0
                continue

            v1 = s1[-min_len:]
            v2 = s2[-min_len:]
            mean1 = sum(v1) / min_len
            mean2 = sum(v2) / min_len

            cov = sum((v1[idx] - mean1) * (v2[idx] - mean2) for idx in range(min_len)) / (min_len - 1)
            var1 = sum((x - mean1) ** 2 for x in v1) / (min_len - 1)
            var2 = sum((y - mean2) ** 2 for y in v2) / (min_len - 1)

            denom = math.sqrt(var1 * var2)
            if denom <= 1e-12:
                result[(k1, k2)] = 0.0
            else:
                result[(k1, k2)] = max(-1.0, min(1.0, cov / denom))
    return result


def is_high_vol_regime(short_vol: float, long_vol: float, threshold: float = 1.5) -> bool:
    """Determine volatility regime switch: sigma_20 / sigma_252 > 1.5 -> high-vol regime."""
    if long_vol <= 1e-12:
        return False
    return (short_vol / long_vol) > threshold
