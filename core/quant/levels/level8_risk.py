"""Level 8: Portfolio & Risk Engine (Formulas 8.1 - 8.5).

Formulas:
8.1 CAPM: E[R_i] = R_f + beta_i * (E[R_m] - R_f), beta_i = Cov(R_i, R_m) / Var(R_m)
8.2 Fama-French 3-Factor: R_i - R_f = alpha_i + beta_1 * MKT + beta_2 * SMB + beta_3 * HML + eps
8.3 Sharpe Ratio: SR = (mean(r) - r_f) / sigma * sqrt(bars_per_year)
8.4 Kelly Criterion: Discrete f* = (b*p - q) / b; Continuous f* = (mu - r_f) / sigma^2
8.5 VaR, Expected Shortfall (CVaR) & Drawdown:
    Parametric VaR_95 = 1.645 * sigma * V
    Expected Shortfall ES_95 = (sigma * phi(1.645) / 0.05) * V
    Max Drawdown MDD = (peak - trough) / peak
"""

import math
from typing import Sequence, Tuple
import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Formula 8.1: Capital Asset Pricing Model (CAPM)
# ---------------------------------------------------------------------------
def compute_capm_beta(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
) -> float:
    """Calculate CAPM beta: beta = Cov(R_i, R_m) / Var(R_m)."""
    n = min(len(asset_returns), len(market_returns))
    if n < 2:
        return 0.0

    r_a = np.asarray(asset_returns[:n], dtype=float)
    r_m = np.asarray(market_returns[:n], dtype=float)

    var_m = float(np.var(r_m, ddof=1))
    if var_m <= 1e-12:
        return 0.0

    cov_am = float(np.cov(r_a, r_m, ddof=1)[0, 1])
    return cov_am / var_m


def compute_capm_expected_return(
    rf: float,
    beta: float,
    market_return: float,
) -> float:
    """Calculate expected return via Security Market Line: E[R_i] = R_f + beta_i * (E[R_m] - R_f)."""
    return rf + beta * (market_return - rf)


def compute_capm(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
    rf: float = 0.0,
) -> dict[str, float]:
    """Compute full CAPM decomposition: beta, alpha, expected return, and R^2."""
    n = min(len(asset_returns), len(market_returns))
    if n < 2:
        return {"beta": 0.0, "alpha": 0.0, "expected_return": rf, "r_squared": 0.0}

    r_a = np.asarray(asset_returns[:n], dtype=float)
    r_m = np.asarray(market_returns[:n], dtype=float)

    var_m = float(np.var(r_m, ddof=1))
    var_a = float(np.var(r_a, ddof=1))
    if var_m <= 1e-12:
        return {"beta": 0.0, "alpha": 0.0, "expected_return": rf, "r_squared": 0.0}

    cov_matrix = np.cov(r_a, r_m, ddof=1)
    cov_am = float(cov_matrix[0, 1])
    beta = cov_am / var_m

    mean_a = float(np.mean(r_a))
    mean_m = float(np.mean(r_m))
    alpha = mean_a - (rf + beta * (mean_m - rf))
    exp_ret = rf + beta * (mean_m - rf)

    if var_a > 1e-12 and var_m > 1e-12:
        corr = cov_am / math.sqrt(var_a * var_m)
        r_squared = float(np.clip(corr ** 2, 0.0, 1.0))
    else:
        r_squared = 0.0

    return {
        "beta": float(beta),
        "alpha": float(alpha),
        "expected_return": float(exp_ret),
        "r_squared": float(r_squared),
    }


# ---------------------------------------------------------------------------
# Formula 8.2: Fama-French 3-Factor Model
# ---------------------------------------------------------------------------
def compute_fama_french_3factor(
    asset_returns: Sequence[float],
    mkt_factor: Sequence[float],
    smb_factor: Sequence[float],
    hml_factor: Sequence[float],
    rf: float = 0.0,
) -> dict[str, float]:
    """Calculate Fama-French 3-Factor regression parameters.

    Model: R_i - R_f = alpha + beta_mkt * MKT + beta_smb * SMB + beta_hml * HML + eps
    """
    n = min(len(asset_returns), len(mkt_factor), len(smb_factor), len(hml_factor))
    empty_result = {
        "alpha": 0.0,
        "beta_mkt": 0.0,
        "beta_smb": 0.0,
        "beta_hml": 0.0,
        "r_squared": 0.0,
        "residual_variance": 0.0,
    }
    if n < 4:
        return empty_result

    y = np.asarray(asset_returns[:n], dtype=float) - rf
    x = np.column_stack([
        np.ones(n, dtype=float),
        np.asarray(mkt_factor[:n], dtype=float),
        np.asarray(smb_factor[:n], dtype=float),
        np.asarray(hml_factor[:n], dtype=float),
    ])

    try:
        # Solve OLS via least squares
        coeffs, residuals, rank, _ = np.linalg.lstsq(x, y, rcond=None)
        if rank < 4:
            return empty_result

        alpha = float(coeffs[0])
        beta_mkt = float(coeffs[1])
        beta_smb = float(coeffs[2])
        beta_hml = float(coeffs[3])

        y_pred = x @ coeffs
        eps = y - y_pred
        ss_res = float(np.sum(eps ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))

        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
        r_squared = float(np.clip(r_squared, 0.0, 1.0))
        residual_variance = ss_res / (n - 4) if n > 4 else 0.0

        return {
            "alpha": alpha,
            "beta_mkt": beta_mkt,
            "beta_smb": beta_smb,
            "beta_hml": beta_hml,
            "r_squared": r_squared,
            "residual_variance": residual_variance,
        }
    except Exception:
        return empty_result


# ---------------------------------------------------------------------------
# Formula 8.3: Sharpe Ratio
# ---------------------------------------------------------------------------
def compute_sharpe_ratio(
    returns: Sequence[float],
    rf: float = 0.0,
    bars_per_year: int = 365,
) -> float:
    """Calculate annualized Sharpe Ratio: SR = (mean(r) - r_f) / sigma * sqrt(bars_per_year)."""
    n = len(returns)
    if n < 2:
        return 0.0

    r = np.asarray(returns, dtype=float)
    excess = r - (rf / bars_per_year)
    mean_excess = float(np.mean(excess))
    vol = float(np.std(excess, ddof=1))

    if vol <= 1e-12:
        return 0.0

    return (mean_excess / vol) * math.sqrt(bars_per_year)


def compute_annualized_risk_adjusted_metrics(
    returns: Sequence[float],
    rf: float = 0.0,
    bars_per_year: int = 365,
) -> dict[str, float]:
    """Calculate comprehensive annualized risk-adjusted return metrics."""
    n = len(returns)
    if n < 2:
        return {"sharpe_ratio": 0.0, "annualized_return": 0.0, "annualized_vol": 0.0}

    r = np.asarray(returns, dtype=float)
    ann_return = float(np.mean(r)) * bars_per_year
    ann_vol = float(np.std(r, ddof=1)) * math.sqrt(bars_per_year)
    sr = compute_sharpe_ratio(returns, rf=rf, bars_per_year=bars_per_year)

    return {
        "sharpe_ratio": sr,
        "annualized_return": ann_return,
        "annualized_vol": ann_vol,
    }


# ---------------------------------------------------------------------------
# Formula 8.4: Kelly Criterion (Discrete & Continuous)
# ---------------------------------------------------------------------------
def compute_discrete_kelly(
    win_prob: float,
    payoff_ratio: float,
    fraction: float = 1.0,
    half_kelly: bool = False,
    max_leverage: float = 2.0,
) -> float:
    """Calculate discrete Kelly bet size fraction: f* = (b*p - q) / b."""
    if payoff_ratio <= 1e-12:
        return 0.0

    p = max(0.0, min(1.0, win_prob))
    q = 1.0 - p
    f_star = (payoff_ratio * p - q) / payoff_ratio

    if f_star <= 0.0:
        return 0.0

    mult = 0.5 if half_kelly else fraction
    f_scaled = f_star * mult
    return float(np.clip(f_scaled, 0.0, max_leverage))


def compute_continuous_kelly(
    mean_return: float,
    vol: float,
    rf: float = 0.0,
    fraction: float = 1.0,
    half_kelly: bool = False,
    max_leverage: float = 3.0,
) -> float:
    """Calculate continuous Kelly optimal leverage: f* = (mu - r_f) / sigma^2."""
    var = vol ** 2
    if var <= 1e-12:
        return 0.0

    f_star = (mean_return - rf) / var
    if f_star <= 0.0:
        return 0.0

    mult = 0.5 if half_kelly else fraction
    f_scaled = f_star * mult
    return float(np.clip(f_scaled, 0.0, max_leverage))


# ---------------------------------------------------------------------------
# Formula 8.5: VaR, Expected Shortfall (CVaR) & Drawdown
# ---------------------------------------------------------------------------
def compute_parametric_var(
    portfolio_value: float,
    vol: float,
    confidence: float = 0.95,
) -> float:
    """Calculate Parametric Value at Risk (VaR): VaR = z_alpha * sigma * V."""
    if portfolio_value <= 0.0 or vol <= 0.0:
        return 0.0
    z = float(stats.norm.ppf(confidence))
    return z * vol * portfolio_value


def compute_expected_shortfall(
    portfolio_value: float,
    vol: float,
    confidence: float = 0.95,
) -> float:
    """Calculate Parametric Expected Shortfall (CVaR): ES = (sigma * phi(z) / (1 - alpha)) * V."""
    if portfolio_value <= 0.0 or vol <= 0.0 or confidence >= 1.0:
        return 0.0

    alpha = confidence
    z = float(stats.norm.ppf(alpha))
    phi_z = float(stats.norm.pdf(z))
    tail_prob = 1.0 - alpha
    return (vol * phi_z / tail_prob) * portfolio_value


def compute_historical_var_cvar(
    returns: Sequence[float],
    portfolio_value: float,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Calculate non-parametric Historical VaR and CVaR (Expected Shortfall)."""
    if not returns or portfolio_value <= 0.0:
        return 0.0, 0.0

    losses = np.sort(-np.asarray(returns, dtype=float) * portfolio_value)
    n = len(losses)
    # Quantile index for confidence level
    idx = int(np.floor(confidence * n))
    idx = min(idx, n - 1)
    var = float(losses[idx])

    tail_losses = losses[idx:]
    cvar = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var

    return var, cvar


def compute_max_drawdown(
    equity_series: Sequence[float],
) -> Tuple[float, float, float]:
    """Calculate maximum peak-to-trough drawdown fraction, peak, and trough values.

    Returns (max_dd_fraction, peak_value, trough_value).
    """
    if not equity_series:
        return 0.0, 0.0, 0.0
    if len(equity_series) == 1:
        return 0.0, equity_series[0], equity_series[0]

    peak = equity_series[0]
    max_dd = 0.0
    best_peak = peak
    best_trough = peak

    for val in equity_series:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 1e-12 else 0.0
        if dd > max_dd:
            max_dd = dd
            best_peak = peak
            best_trough = val

    return float(max_dd), float(best_peak), float(best_trough)
