"""Statistical Arbitrage, Cointegration, and Ornstein-Uhlenbeck Mean Reversion Engine.

Designed for 24/7 cryptocurrency pairs trading (e.g. ETH/BTC, SOL/ETH, AVAX/SOL).
Implements:
1. Ordinary Least Squares (OLS) dynamic hedge ratio (beta) estimation.
2. Engle-Granger cointegration stationarity testing via ADF unit-root t-statistics.
3. Ornstein-Uhlenbeck (OU) continuous parameter estimation (theta, mu, sigma, half-life).
4. Rolling standardized Z-score spread computation and mean-reversion trading signals.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


def calculate_hedge_ratio(series_a: List[float], series_b: List[float]) -> Tuple[float, float]:
    """Calculate OLS hedge ratio: log(P_A) = alpha + beta * log(P_B) + epsilon.
    
    Returns (beta, alpha).
    """
    n = min(len(series_a), len(series_b))
    if n < 5:
        return 1.0, 0.0

    y = np.log(np.maximum(series_a[-n:], 1e-8))
    x = np.log(np.maximum(series_b[-n:], 1e-8))

    x_mean = np.mean(x)
    y_mean = np.mean(y)

    cov_xy = np.sum((x - x_mean) * (y - y_mean))
    var_x = np.sum((x - x_mean) ** 2)

    if var_x < 1e-12:
        return 1.0, 0.0

    beta = float(cov_xy / var_x)
    alpha = float(y_mean - beta * x_mean)
    return round(beta, 6), round(alpha, 6)


def calculate_spread(
    series_a: List[float],
    series_b: List[float],
    beta: Optional[float] = None,
    alpha: Optional[float] = None,
) -> np.ndarray:
    """Calculate spread: S_t = log(P_A) - beta * log(P_B) - alpha."""
    n = min(len(series_a), len(series_b))
    if n == 0:
        return np.array([], dtype=float)

    if beta is None or alpha is None:
        calc_beta, calc_alpha = calculate_hedge_ratio(series_a[-n:], series_b[-n:])
        beta = beta if beta is not None else calc_beta
        alpha = alpha if alpha is not None else calc_alpha

    y = np.log(np.maximum(series_a[-n:], 1e-8))
    x = np.log(np.maximum(series_b[-n:], 1e-8))
    return y - (beta * x) - alpha


def adf_unit_root_test(residuals: np.ndarray, max_lags: int = 1) -> Tuple[float, float, bool]:
    """Augmented Dickey-Fuller (ADF) regression test on residuals.
    
    Regression: Delta e_t = gamma * e_{t-1} + sum(psi_i * Delta e_{t-i}) + error
    Tests H0: gamma = 0 (unit root, non-stationary) vs H1: gamma < 0 (stationary).
    
    Returns (t_stat, p_value_approx, is_stationary_95pct).
    """
    n = len(residuals)
    if n < 15:
        return 0.0, 1.0, False

    diff = np.diff(residuals)
    # Target: diff[1:]
    # Regressors: residuals[:-1], and lagged diffs
    y = diff[max_lags:]
    x_lag = residuals[max_lags:-1]

    regressors = [x_lag]
    for lag in range(1, max_lags + 1):
        regressors.append(diff[max_lags - lag : -lag])

    X = np.column_stack(regressors)
    
    # OLS estimation: (X'X)^-1 X'y
    try:
        XtX = X.T @ X
        if np.linalg.cond(XtX) > 1e10:
            return 0.0, 1.0, False
        params = np.linalg.solve(XtX, X.T @ y)
        gamma = params[0]

        residuals_ols = y - X @ params
        df = len(y) - X.shape[1]
        if df <= 0:
            return 0.0, 1.0, False

        sigma2 = np.sum(residuals_ols ** 2) / df
        cov_matrix = sigma2 * np.linalg.inv(XtX)
        se_gamma = math.sqrt(max(cov_matrix[0, 0], 1e-12))

        t_stat = gamma / se_gamma

        # MacKinnon critical values for Engle-Granger 2-variable test:
        # 1%: -3.90, 5%: -3.34, 10%: -3.04
        is_stationary = t_stat < -3.34

        # Approximate p-value mapping
        if t_stat < -3.90:
            p_val = 0.01
        elif t_stat < -3.34:
            p_val = 0.05 - (0.04 * (abs(t_stat) - 3.34) / (3.90 - 3.34))
        elif t_stat < -3.04:
            p_val = 0.10 - (0.05 * (abs(t_stat) - 3.04) / (3.34 - 3.04))
        else:
            p_val = min(0.99, 0.10 + 0.15 * (t_stat + 3.04))

        return round(float(t_stat), 4), round(float(max(0.001, p_val)), 4), bool(is_stationary)
    except Exception:
        return 0.0, 1.0, False


def ornstein_uhlenbeck_parameters(spread: np.ndarray, dt: float = 1.0) -> Dict[str, float]:
    """Fit continuous Ornstein-Uhlenbeck process dS = theta*(mu - S)*dt + sigma*dW.
    
    Discretized as AR(1): S_t = a + b * S_{t-1} + eps
    theta = -ln(b) / dt
    mu = a / (1 - b)
    sigma = sigma_eps * sqrt(2*theta / (1 - b^2))
    half_life = ln(2) / theta
    """
    n = len(spread)
    if n < 10:
        return {
            "theta": 0.0,
            "mu": 0.0,
            "sigma": 0.0,
            "half_life_bars": 0.0,
            "mean_reverting": False,
        }

    s_curr = spread[1:]
    s_prev = spread[:-1]

    # OLS for s_curr = a + b * s_prev
    X = np.column_stack([np.ones(len(s_prev)), s_prev])
    try:
        a, b = np.linalg.lstsq(X, s_curr, rcond=None)[0]
    except Exception:
        return {
            "theta": 0.0,
            "mu": 0.0,
            "sigma": 0.0,
            "half_life_bars": 0.0,
            "mean_reverting": False,
        }

    # Stationarity requires 0 < b < 1
    if b <= 0.0001 or b >= 0.9999:
        # Non-mean-reverting or explosive
        return {
            "theta": 0.0,
            "mu": float(np.mean(spread)),
            "sigma": float(np.std(spread)),
            "half_life_bars": float("inf"),
            "mean_reverting": False,
        }

    theta = -math.log(b) / dt
    mu = a / (1.0 - b)
    residuals = s_curr - (a + b * s_prev)
    sigma_eps = float(np.std(residuals))
    denom = max(1e-6, 1.0 - (b ** 2))
    sigma = sigma_eps * math.sqrt(2.0 * theta / denom)
    half_life = math.log(2.0) / theta

    return {
        "theta": round(float(theta), 6),
        "mu": round(float(mu), 6),
        "sigma": round(float(sigma), 6),
        "half_life_bars": round(float(half_life), 2),
        "mean_reverting": bool(0.5 <= half_life <= 500.0),
    }


def calculate_spread_zscore(
    series_a: List[float],
    series_b: List[float],
    window: int = 30,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.25,
    stop_threshold: float = 3.5,
) -> Dict[str, Any]:
    """Compute rolling standardized Z-score of spread and trade recommendation."""
    n = min(len(series_a), len(series_b))
    if n < window + 5:
        return {
            "zscore": 0.0,
            "spread": 0.0,
            "rolling_mean": 0.0,
            "rolling_std": 0.0,
            "beta": 1.0,
            "alpha": 0.0,
            "signal": "INSUFFICIENT_DATA",
            "action": "HOLD",
        }

    beta, alpha = calculate_hedge_ratio(series_a[-window*3:], series_b[-window*3:])
    spread = calculate_spread(series_a, series_b, beta=beta, alpha=alpha)

    rolling_window = spread[-window:]
    mean = float(np.mean(rolling_window))
    std = float(np.std(rolling_window))

    curr_spread = float(spread[-1])
    if std < 1e-8:
        zscore = 0.0
    else:
        zscore = float((curr_spread - mean) / std)

    zscore = round(zscore, 4)

    # Signal generation logic:
    # Z <= -entry_threshold -> Spread undervalued: Long A, Short B
    # Z >= +entry_threshold -> Spread overvalued: Short A, Long B
    # |Z| <= exit_threshold -> Mean reached: Close / Take Profit
    # |Z| >= stop_threshold -> Regime break: Hard Stop-Loss
    if abs(zscore) >= stop_threshold:
        signal = "STRUCTURAL_BREAK_STOP"
        action = "FLATTEN"
    elif zscore <= -entry_threshold:
        signal = "LONG_SPREAD_ENTRY"
        action = "BUY_A_SELL_B"
    elif zscore >= entry_threshold:
        signal = "SHORT_SPREAD_ENTRY"
        action = "SELL_A_BUY_B"
    elif abs(zscore) <= exit_threshold:
        signal = "EQUILIBRIUM_EXIT"
        action = "CLOSE_TARGET"
    else:
        signal = "IN_CHANNEL"
        action = "HOLD"

    return {
        "zscore": zscore,
        "spread": round(curr_spread, 6),
        "rolling_mean": round(mean, 6),
        "rolling_std": round(std, 6),
        "beta": beta,
        "alpha": alpha,
        "signal": signal,
        "action": action,
    }


def analyze_crypto_pair(
    candles_a: List[Dict[str, Any]],
    candles_b: List[Dict[str, Any]],
    symbol_a: str = "ETHUSDT",
    symbol_b: str = "BTCUSDT",
    window: int = 30,
) -> Dict[str, Any]:
    """Execute complete statistical arbitrage diagnostic on two crypto candle series."""
    # Align candles by timestamp
    ts_map_b = {int(c["close_time"]): float(c["close"]) for c in candles_b}
    
    aligned_a = []
    aligned_b = []
    
    for c in candles_a:
        ts = int(c["close_time"])
        if ts in ts_map_b:
            aligned_a.append(float(c["close"]))
            aligned_b.append(ts_map_b[ts])

    if len(aligned_a) < window + 5:
        # Fallback to direct tail alignment if close times differ slightly across feeds
        n = min(len(candles_a), len(candles_b))
        aligned_a = [float(c["close"]) for c in candles_a[-n:]]
        aligned_b = [float(c["close"]) for c in candles_b[-n:]]

    if len(aligned_a) < 15:
        return {
            "pair": f"{symbol_a} / {symbol_b}",
            "status": "INSUFFICIENT_DATA",
            "samples": len(aligned_a),
        }

    beta, alpha = calculate_hedge_ratio(aligned_a, aligned_b)
    spread = calculate_spread(aligned_a, aligned_b, beta=beta, alpha=alpha)

    # Unit root / Cointegration test
    t_stat, p_val, is_coint = adf_unit_root_test(spread)

    # OU parameters
    ou_metrics = ornstein_uhlenbeck_parameters(spread)

    # Z-Score and signal
    z_metrics = calculate_spread_zscore(aligned_a, aligned_b, window=window)

    # Correlation
    r_corr = float(np.corrcoef(aligned_a, aligned_b)[0, 1]) if len(aligned_a) > 2 else 0.0

    return {
        "pair": f"{symbol_a}/{symbol_b}",
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "samples_aligned": len(aligned_a),
        "correlation": round(r_corr, 4),
        "hedge_ratio_beta": beta,
        "alpha": alpha,
        "cointegration": {
            "is_cointegrated": is_coint,
            "adf_t_stat": t_stat,
            "p_value": p_val,
            "critical_val_5pct": -3.34,
        },
        "ornstein_uhlenbeck": ou_metrics,
        "current_spread": z_metrics["spread"],
        "zscore": z_metrics["zscore"],
        "signal": z_metrics["signal"],
        "recommended_action": z_metrics["action"],
    }
