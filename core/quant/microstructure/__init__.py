"""Microstructure package for institutional quantitative order flow, market making, and execution protections."""

from .order_flow import (
    compute_cumulative_volume_delta,
    compute_cvd_from_trades,
    compute_cvd_from_candles,
    detect_delta_divergence,
    detect_absorption,
    OrderFlowScreener,
    DivergenceType,
    AbsorptionType,
)
from .market_making import (
    compute_reservation_price,
    compute_optimal_spread,
    compute_avellaneda_stoikov_quotes,
    compute_inventory_skewed_sizes,
    AvellanedaStoikovMarketMaker,
)
from .protections import (
    CooldownPeriodGuard,
    ConsecutiveStoplossGuard,
    BracketOrderSimulator,
    BracketOrderStatus,
    OrderSide,
)

__all__ = [
    "compute_cumulative_volume_delta",
    "compute_cvd_from_trades",
    "compute_cvd_from_candles",
    "detect_delta_divergence",
    "detect_absorption",
    "OrderFlowScreener",
    "DivergenceType",
    "AbsorptionType",
    "compute_reservation_price",
    "compute_optimal_spread",
    "compute_avellaneda_stoikov_quotes",
    "compute_inventory_skewed_sizes",
    "AvellanedaStoikovMarketMaker",
    "CooldownPeriodGuard",
    "ConsecutiveStoplossGuard",
    "BracketOrderSimulator",
    "BracketOrderStatus",
    "OrderSide",
]
