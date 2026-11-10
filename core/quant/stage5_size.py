r"""Stage 5: Position Sizing Engine (Formulas 5.1 - 5.6).

Formulas:
5.1 Risk-based size: size = equity * risk% / |entry - stop|
5.2 Kelly criterion: f* = p - (1 - p) / b
5.3 Continuous Kelly: f* = mu / sigma^2
5.4 Volatility target: w = sigma_target / sigma_realized
5.5 Risk parity: w_i \propto 1 / sigma_i
5.6 Liquidation price: P_liq \approx P_entry * (1 - 1/L + mmr)
"""

from typing import Mapping


def compute_risk_based_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
) -> float:
    """Calculate fixed-fractional risk position size: size = equity * risk% / |entry - stop|."""
    risk_dollars = equity * risk_pct
    stop_distance = abs(entry - stop)
    if stop_distance <= 1e-12:
        return 0.0
    return risk_dollars / stop_distance


def compute_kelly_criterion(
    win_prob: float,
    payoff_b: float,
    fraction: float = 0.5,
) -> float:
    """Calculate discrete Kelly bet size fraction: f* = fraction * (p - (1 - p) / b)."""
    if payoff_b <= 1e-12:
        return 0.0
    p = max(0.0, min(1.0, win_prob))
    f_star = p - ((1.0 - p) / payoff_b)
    return max(0.0, f_star * fraction)


def compute_continuous_kelly(
    mean_return: float,
    var_return: float,
    fraction: float = 0.5,
) -> float:
    """Calculate continuous Kelly leverage: f* = fraction * (mu / sigma^2)."""
    if var_return <= 1e-12:
        return 0.0
    f_star = mean_return / var_return
    return max(0.0, f_star * fraction)


def compute_volatility_target_weight(
    target_vol: float,
    realized_vol: float,
    max_leverage: float = 3.0,
) -> float:
    """Calculate Volatility Targeting position scalar: w = min(max_leverage, target_vol / realized_vol)."""
    if realized_vol <= 1e-12:
        return 0.0
    w = target_vol / realized_vol
    return max(0.0, min(max_leverage, w))


def compute_risk_parity_weights(volatilities: Mapping[str, float]) -> dict[str, float]:
    r"""Calculate inverse-volatility Risk Parity weights: w_i \propto 1 / sigma_i."""
    inv_vols: dict[str, float] = {}
    for asset, vol in volatilities.items():
        if vol > 1e-12:
            inv_vols[asset] = 1.0 / vol
        else:
            inv_vols[asset] = 0.0

    total_inv = sum(inv_vols.values())
    if total_inv <= 1e-12:
        n = len(volatilities)
        return {asset: 1.0 / n if n > 0 else 0.0 for asset in volatilities}

    return {asset: inv / total_inv for asset, inv in inv_vols.items()}


def compute_liquidation_price(
    entry: float,
    leverage: float,
    mmr: float = 0.005,
    is_long: bool = True,
) -> float:
    """Calculate estimated exchange liquidation price.

    Long: P_liq \approx P_entry * (1 - 1/L + mmr)
    Short: P_liq \approx P_entry * (1 + 1/L - mmr)
    """
    if leverage <= 0.0:
        return 0.0
    inv_l = 1.0 / leverage
    if is_long:
        return entry * (1.0 - inv_l + mmr)
    else:
        return entry * (1.0 + inv_l - mmr)
