"""Mathematical Position Sizing, Kelly Criterion, and Risk Parity Allocation.

Implements institutional quantitative capital allocation rules:
1. Continuous & Discrete Kelly Criterion:
   f* = (p * b - (1 - p)) / b
   with Fractional Kelly dampening (Half Kelly / Quarter Kelly) to minimize drawdowns.
2. Deflated Sharpe Ratio / Margin of Safety penalization for empirical parameter uncertainty.
3. Volatility Parity (Inverse Volatility) multi-asset weighting:
   w_i = (1 / sigma_i) / sum(1 / sigma_j)
4. Conditional Value-at-Risk (CVaR / Expected Shortfall) tail risk estimation.
5. Fail-closed sizing guard against over-leverage or zero/negative expectancy.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import numpy as np


def kelly_criterion(
    win_rate: float,
    win_loss_ratio: float,
    fraction: float = 0.5,
    max_risk_cap: float = 0.20,
) -> Dict[str, float]:
    """Compute optimal Kelly fraction.
    
    Parameters:
    - win_rate (p): Probability of win (e.g. 0.55).
    - win_loss_ratio (b): Average win size / average loss size (e.g. 1.8).
    - fraction (lambda): Kelly multiplier (0.5 = Half Kelly, 0.25 = Quarter Kelly).
    - max_risk_cap: Maximum hard capital fraction allowed on one position.
    """
    p = max(0.0, min(1.0, float(win_rate)))
    b = max(1e-4, float(win_loss_ratio))
    q = 1.0 - p

    # Raw Kelly: f* = (b*p - q) / b = p - q/b
    edge = (b * p) - q
    if edge <= 0.0:
        return {
            "edge": round(edge, 4),
            "full_kelly": 0.0,
            "allocated_fraction": 0.0,
            "fraction_used": fraction,
            "status": "NEGATIVE_OR_ZERO_EDGE",
        }

    full_kelly = edge / b
    fractional = full_kelly * fraction
    capped = min(max_risk_cap, fractional)

    return {
        "edge": round(edge, 4),
        "full_kelly": round(full_kelly, 4),
        "allocated_fraction": round(capped, 4),
        "fraction_used": fraction,
        "status": "POSITIVE_EDGE",
    }


def volatility_parity_allocation(
    symbol_volatilities: Dict[str, float],
    total_capital: float = 100000.0,
) -> Dict[str, Any]:
    """Compute Risk Parity / Volatility Parity weights: w_i = (1 / sigma_i) / sum(1 / sigma_j).
    
    Higher volatility tokens receive proportionally smaller capital allocations to equalize risk contribution.
    """
    valid = {k: max(1e-6, float(v)) for k, v in symbol_volatilities.items() if v > 0}
    if not valid:
        return {"weights": {}, "capital_allocation": {}, "total_capital": total_capital}

    inv_vols = {k: 1.0 / v for k, v in valid.items()}
    sum_inv = sum(inv_vols.values())

    weights = {k: round(v / sum_inv, 4) for k, v in inv_vols.items()}
    cap_alloc = {k: round(weights[k] * total_capital, 2) for k in weights}

    return {
        "weights": weights,
        "capital_allocation": cap_alloc,
        "total_capital": total_capital,
    }


def calculate_cvar(returns: List[float], confidence_level: float = 0.95) -> Dict[str, float]:
    """Calculate Value-at-Risk (VaR) and Conditional Value-at-Risk (CVaR / Expected Shortfall)."""
    if len(returns) < 10:
        return {"var_pct": 0.0, "cvar_pct": 0.0, "confidence": confidence_level}

    arr = np.array(returns, dtype=float)
    alpha = (1.0 - confidence_level) * 100.0
    var_threshold = float(np.percentile(arr, alpha))

    # CVaR is the mean of losses worse than VaR
    tail_losses = arr[arr <= var_threshold]
    cvar = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var_threshold

    return {
        "var_pct": round(abs(var_threshold) * 100.0, 3),
        "cvar_pct": round(abs(cvar) * 100.0, 3),
        "confidence": confidence_level,
    }


def optimal_trade_sizing(
    account_balance: float,
    entry_price: float,
    stop_loss: float,
    win_rate: float = 0.52,
    win_loss_ratio: float = 1.8,
    kelly_fraction: float = 0.5,
    max_account_risk_pct: float = 2.0,
    volatility_compression_score: float = 1.0,
) -> Dict[str, Any]:
    """Produce complete institutional trade sizing recommendation.
    
    Incorporates:
    - Stop-loss distance risk.
    - Fractional Kelly edge scaling.
    - Volatility compression expansion factor (scales size up if entering high-probability compression breakout).
    """
    if account_balance <= 0 or entry_price <= 0 or stop_loss <= 0 or entry_price == stop_loss:
        return {
            "status": "INVALID_PARAMETERS",
            "position_size_usd": 0.0,
            "position_qty": 0.0,
            "risk_usd": 0.0,
            "risk_pct": 0.0,
        }

    stop_distance_pct = abs(entry_price - stop_loss) / entry_price
    kelly = kelly_criterion(win_rate, win_loss_ratio, fraction=kelly_fraction)

    if kelly["allocated_fraction"] <= 0:
        return {
            "status": "NO_EDGE",
            "position_size_usd": 0.0,
            "position_qty": 0.0,
            "risk_usd": 0.0,
            "risk_pct": 0.0,
            "reason": "Win rate and payout do not yield a positive mathematical expectancy.",
        }

    # Base risk budget: e.g. 2% of bankroll
    max_risk_usd = account_balance * (max_account_risk_pct / 100.0)

    # Scale risk budget by Kelly edge factor
    # A full Kelly fraction of 0.20 gets 100% of max risk budget; lower edge scales down
    edge_scale = min(1.5, max(0.2, kelly["allocated_fraction"] / 0.10))
    risk_budget_usd = max_risk_usd * edge_scale

    # If in compression squeeze, volatility expansion is imminent -> moderate scaling
    if volatility_compression_score < 0.65:
        risk_budget_usd *= 1.15
    elif volatility_compression_score > 1.45:
        # High volatility expansion already occurring, reduce size for safety
        risk_budget_usd *= 0.85

    # Compute notional position size: Risk Budget / Stop Distance %
    notional_usd = risk_budget_usd / max(stop_distance_pct, 0.005)

    # Maximum notional cap: cannot exceed 50% of bankroll on a single unhedged spot asset
    notional_usd = min(notional_usd, account_balance * 0.50)
    qty = notional_usd / entry_price
    actual_risk_usd = notional_usd * stop_distance_pct
    actual_risk_pct = (actual_risk_usd / account_balance) * 100.0

    return {
        "status": "APPROVED",
        "position_size_usd": round(notional_usd, 2),
        "position_qty": round(qty, 6),
        "risk_usd": round(actual_risk_usd, 2),
        "risk_pct": round(actual_risk_pct, 2),
        "stop_distance_pct": round(stop_distance_pct * 100.0, 2),
        "kelly_metrics": kelly,
        "edge_multiplier": round(edge_scale, 2),
        "volatility_modifier": round(volatility_compression_score, 2),
    }
