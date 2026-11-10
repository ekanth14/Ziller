r"""Stage 6: Execution Analysis & TCA Engine (Formulas 6.1 - 6.6).

Formulas:
6.1 Spread cost: spread = (ask - bid) / mid
6.2 Microprice: P_micro = (P_b * Q_a + P_a * Q_b) / (Q_a + Q_b)
6.3 Square-root impact: Delta P / P \approx sigma * sqrt(Q / V)
6.4 VWAP: VWAP = \sum p_i * q_i / \sum q_i
6.5 Slippage: slip = (fill - expected) / expected
6.6 Maker vs taker: round_trip = 2 * fee
"""

import math
from typing import Sequence, Tuple


def compute_spread_cost(bid: float, ask: float) -> Tuple[float, float]:
    """Calculate relative bid-ask spread and half-spread cost: spread = (ask - bid) / mid."""
    mid = (ask + bid) / 2.0
    if mid <= 1e-12:
        return 0.0, 0.0
    spread = (ask - bid) / mid
    half_spread = spread / 2.0
    return spread, half_spread


def compute_microprice(
    bid_price: float,
    bid_qty: float,
    ask_price: float,
    ask_qty: float,
    last_price: float | None = None,
) -> float:
    """Calculate volume-weighted microprice: P_micro = (P_b * Q_a + P_a * Q_b) / (Q_a + Q_b).

    Leans towards the heavier side of the order book.
    If order book is empty (total_qty <= 1e-12), falls back to last_price if provided and > 0,
    otherwise mid price (bid + ask) / 2.0.
    """
    total_qty = bid_qty + ask_qty
    if total_qty <= 1e-12:
        if last_price is not None and last_price > 0.0:
            return float(last_price)
        return (bid_price + ask_price) / 2.0
    # Note weights: bid price is weighted by ask quantity, ask price by bid quantity
    return ((bid_price * ask_qty) + (ask_price * bid_qty)) / total_qty


def compute_square_root_impact(
    volatility: float,
    order_qty: float,
    daily_volume: float,
    impact_constant: float = 1.0,
) -> float:
    """Calculate Square-Root Law market impact estimate: Delta P / P \approx c * sigma * sqrt(Q / V)."""
    if daily_volume <= 1e-12 or order_qty <= 0.0:
        return 0.0
    ratio = order_qty / daily_volume
    return impact_constant * volatility * math.sqrt(ratio)


def compute_vwap(trades: Sequence[Tuple[float, float]]) -> float:
    r"""Calculate Volume Weighted Average Price (VWAP): VWAP = \sum p_i * q_i / \sum q_i."""
    if not trades:
        return 0.0
    total_dollar_vol = sum(p * q for p, q in trades)
    total_volume = sum(q for _, q in trades)
    if total_volume <= 1e-12:
        return 0.0
    return total_dollar_vol / total_volume


def compute_slippage(expected_price: float, filled_price: float) -> float:
    """Calculate realized execution slippage fraction: slip = (fill - expected) / expected."""
    if expected_price <= 1e-12:
        return 0.0
    return (filled_price - expected_price) / expected_price


def compute_round_trip_fee(fee_rate: float) -> float:
    """Calculate 2-sided round trip fee cost: round_trip = 2 * fee."""
    return 2.0 * fee_rate
