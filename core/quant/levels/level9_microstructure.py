"""Level 9: Microstructure & Execution Engine (Formulas 9.1 - 9.5).

Formulas:
9.1 Spread & Mid: mid = (P_a + P_b) / 2, spread = (P_a - P_b) / mid, half_spread = spread / 2
9.2 Order Book Imbalance & Microprice:
    I = (Q_b - Q_a) / (Q_b + Q_a), P_micro = (P_b * Q_a + P_a * Q_b) / (Q_b + Q_a)
    (with last_price fallback on thin books)
9.3 Square-Root Impact: Delta P / P \approx c * sigma * sqrt(Q / V)
9.4 VWAP, TWAP & Implementation Shortfall:
    VWAP = sum(p_i * q_i) / sum(q_i), TWAP = (1/N) * sum(p_i)
    Implementation Shortfall = P_executed - P_decision (buy) or P_decision - P_executed (sell)
9.5 Avellaneda-Stoikov Market Making:
    Reservation price: r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
    Optimal spread: delta = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / kappa)
    Quotes: r_bid = r - delta / 2, r_ask = r + delta / 2
"""

import math
from typing import Sequence, Tuple


# ---------------------------------------------------------------------------
# Formula 9.1: Spread & Mid
# ---------------------------------------------------------------------------
def compute_mid_price(bid: float, ask: float) -> float:
    """Calculate mid price: mid = (ask + bid) / 2."""
    if bid <= 0.0 or ask <= 0.0:
        return 0.0
    return (ask + bid) / 2.0


def compute_spreads(bid: float, ask: float) -> dict[str, float]:
    """Calculate absolute spread, relative spread, and half-spread cost.

    Guards against zero mid price and crossed book (bid > ask).
    """
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        mid = (ask + bid) / 2.0 if (bid > 0.0 and ask > 0.0) else 0.0
        return {
            "mid": mid,
            "abs_spread": 0.0,
            "rel_spread": 0.0,
            "half_spread": 0.0,
        }

    mid = (ask + bid) / 2.0
    abs_spread = ask - bid
    rel_spread = abs_spread / mid if mid > 1e-12 else 0.0
    half_spread = rel_spread / 2.0

    return {
        "mid": mid,
        "abs_spread": abs_spread,
        "rel_spread": rel_spread,
        "half_spread": half_spread,
    }


# ---------------------------------------------------------------------------
# Formula 9.2: Order Book Imbalance & Microprice
# ---------------------------------------------------------------------------
def compute_order_book_imbalance(
    bid_qty: float,
    ask_qty: float,
) -> float:
    """Calculate Order Book Imbalance: I = (Q_b - Q_a) / (Q_b + Q_a) in [-1.0, 1.0]."""
    total_qty = bid_qty + ask_qty
    if total_qty <= 1e-12:
        return 0.0
    return (bid_qty - ask_qty) / total_qty


def compute_multilevel_imbalance(
    bids: Sequence[Tuple[float, float]],
    asks: Sequence[Tuple[float, float]],
    depth: int = 5,
) -> float:
    """Calculate cumulative order book imbalance across top L depth levels."""
    n_bids = min(len(bids), depth)
    n_asks = min(len(asks), depth)

    sum_bid_qty = sum(qty for _, qty in bids[:n_bids])
    sum_ask_qty = sum(qty for _, qty in asks[:n_asks])

    total_qty = sum_bid_qty + sum_ask_qty
    if total_qty <= 1e-12:
        return 0.0
    return (sum_bid_qty - sum_ask_qty) / total_qty


def compute_microprice(
    bid_price: float,
    bid_qty: float,
    ask_price: float,
    ask_qty: float,
    last_price: float | None = None,
    min_depth: float = 1e-12,
) -> float:
    """Calculate inventory-weighted microprice: P_micro = (P_b * Q_a + P_a * Q_b) / (Q_a + Q_b).

    Safe fallback on thin order books:
    - If total depth (bid_qty + ask_qty) <= min_depth:
      1) Falls back to last_price if provided and > 0
      2) Otherwise falls back to mid price (bid_price + ask_price) / 2.0
    """
    total_depth = bid_qty + ask_qty
    if total_depth <= min_depth:
        if last_price is not None and last_price > 0.0:
            return float(last_price)
        return (bid_price + ask_price) / 2.0

    return (bid_price * ask_qty + ask_price * bid_qty) / total_depth


# ---------------------------------------------------------------------------
# Formula 9.3: Square-Root Impact
# ---------------------------------------------------------------------------
def compute_square_root_impact(
    volatility: float,
    order_qty: float,
    market_volume: float,
    impact_constant: float = 1.0,
    current_price: float = 1.0,
) -> dict[str, float]:
    """Calculate Square-Root Law market impact: Delta P / P = c * sigma * sqrt(Q / V)."""
    if market_volume <= 1e-12 or order_qty <= 0.0 or volatility <= 0.0:
        return {
            "relative_impact": 0.0,
            "absolute_impact": 0.0,
            "expected_execution_price": current_price,
        }

    participation = order_qty / market_volume
    rel_impact = impact_constant * volatility * math.sqrt(participation)
    abs_impact = current_price * rel_impact
    expected_exec = current_price + abs_impact

    return {
        "relative_impact": rel_impact,
        "absolute_impact": abs_impact,
        "expected_execution_price": expected_exec,
    }


# ---------------------------------------------------------------------------
# Formula 9.4: VWAP, TWAP & Implementation Shortfall
# ---------------------------------------------------------------------------
def compute_vwap(trades: Sequence[Tuple[float, float]]) -> float:
    """Calculate Volume Weighted Average Price: VWAP = sum(p_i * q_i) / sum(q_i)."""
    if not trades:
        return 0.0

    total_dollar_vol = sum(p * q for p, q in trades)
    total_vol = sum(q for _, q in trades)

    if total_vol <= 1e-12:
        return 0.0

    return total_dollar_vol / total_vol


def compute_twap(
    prices: Sequence[float],
    intervals: Sequence[float] | None = None,
) -> float:
    """Calculate Time Weighted Average Price: TWAP = (1/N) * sum(p_i) or weighted by intervals."""
    if not prices:
        return 0.0

    if intervals is None:
        return sum(prices) / len(prices)

    n = min(len(prices), len(intervals))
    if n == 0:
        return 0.0

    total_time = sum(intervals[:n])
    if total_time <= 1e-12:
        return sum(prices[:n]) / n

    return sum(prices[i] * intervals[i] for i in range(n)) / total_time


def compute_implementation_shortfall(
    decision_price: float,
    execution_price: float,
    side: str = "BUY",
    quantity: float = 1.0,
) -> dict[str, float]:
    """Calculate Implementation Shortfall: P_executed - P_decision (buy) or P_decision - P_executed (sell)."""
    if side.upper() == "BUY":
        shortfall = execution_price - decision_price
    else:
        shortfall = decision_price - execution_price

    if decision_price > 1e-12:
        shortfall_bps = (shortfall / decision_price) * 10000.0
    else:
        shortfall_bps = 0.0

    total_cost = shortfall * quantity

    return {
        "shortfall": shortfall,
        "shortfall_bps": shortfall_bps,
        "total_cost": total_cost,
    }


# ---------------------------------------------------------------------------
# Formula 9.5: Avellaneda-Stoikov Market Making
# ---------------------------------------------------------------------------
def compute_avellaneda_stoikov(
    mid_price: float,
    inventory: float,
    gamma: float = 0.1,
    sigma: float = 0.02,
    time_horizon: float = 1.0,
    kappa: float = 1.5,
) -> dict[str, float]:
    """Calculate Avellaneda-Stoikov reservation price and optimal quoting spreads.

    r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
    delta = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / kappa)
    r_bid = r - delta / 2
    r_ask = r + delta / 2
    """
    t_rem = max(0.0, time_horizon)
    vol_term = gamma * (sigma ** 2) * t_rem

    # Reservation price skewed by inventory
    reservation_price = mid_price - (inventory * vol_term)

    # Optimal total spread
    if gamma > 1e-12 and kappa > 1e-12:
        liquidity_term = (2.0 / gamma) * math.log(1.0 + (gamma / kappa))
    else:
        liquidity_term = 0.0

    optimal_spread = vol_term + liquidity_term
    half_spread = optimal_spread / 2.0

    bid_quote = reservation_price - half_spread
    ask_quote = reservation_price + half_spread

    return {
        "reservation_price": reservation_price,
        "optimal_spread": optimal_spread,
        "bid_quote": bid_quote,
        "ask_quote": ask_quote,
        "half_spread": half_spread,
    }
