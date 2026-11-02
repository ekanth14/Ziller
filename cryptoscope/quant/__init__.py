"""Quantitative Analysis and Algorithmic Trading Engine for ZILLERS Crypto Terminal.

Submodules:
- stat_arb: Cointegration, OLS hedge ratio, Ornstein-Uhlenbeck mean-reversion, spread Z-score.
- volatility: Parkinson, Garman-Klass, Yang-Zhang estimators, compression regime classifier.
- order_flow: Cumulative Volume Delta (CVD), order flow imbalance, absorption divergence.
- sizing: Fractional Kelly criterion, risk parity, volatility parity, CVaR.
"""

from cryptoscope.quant.stat_arb import (
    calculate_hedge_ratio,
    calculate_spread,
    adf_unit_root_test,
    ornstein_uhlenbeck_parameters,
    calculate_spread_zscore,
    analyze_crypto_pair,
)
from cryptoscope.quant.volatility import (
    realized_volatility,
    parkinson_volatility,
    garman_klass_volatility,
    yang_zhang_volatility,
    volatility_regime_analysis,
)
from cryptoscope.quant.order_flow import (
    calculate_cvd,
    detect_cvd_divergence,
    analyze_order_flow,
)
from cryptoscope.quant.sizing import (
    kelly_criterion,
    volatility_parity_allocation,
    calculate_cvar,
    optimal_trade_sizing,
)

__all__ = [
    "calculate_hedge_ratio",
    "calculate_spread",
    "adf_unit_root_test",
    "ornstein_uhlenbeck_parameters",
    "calculate_spread_zscore",
    "analyze_crypto_pair",
    "realized_volatility",
    "parkinson_volatility",
    "garman_klass_volatility",
    "yang_zhang_volatility",
    "volatility_regime_analysis",
    "calculate_cvd",
    "detect_cvd_divergence",
    "analyze_order_flow",
    "kelly_criterion",
    "volatility_parity_allocation",
    "calculate_cvar",
    "optimal_trade_sizing",
]
