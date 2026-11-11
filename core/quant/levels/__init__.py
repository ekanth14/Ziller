"""10-Level Institutional Quant Engine."""

# Level 8: Portfolio & Risk
from core.quant.levels.level8_risk import (
    compute_capm_beta,
    compute_capm_expected_return,
    compute_capm,
    compute_fama_french_3factor,
    compute_sharpe_ratio,
    compute_annualized_risk_adjusted_metrics,
    compute_discrete_kelly,
    compute_continuous_kelly,
    compute_parametric_var,
    compute_expected_shortfall,
    compute_historical_var_cvar,
    compute_max_drawdown,
)

# Level 9: Microstructure & Execution
from core.quant.levels.level9_microstructure import (
    compute_mid_price,
    compute_spreads,
    compute_order_book_imbalance,
    compute_multilevel_imbalance,
    compute_microprice,
    compute_square_root_impact,
    compute_vwap,
    compute_twap,
    compute_implementation_shortfall,
    compute_avellaneda_stoikov,
)

# Level 10: Research & Machine Learning
from core.quant.levels.level10_research import (
    audit_backtest_biases,
    generate_walk_forward_windows,
    compute_walk_forward_efficiency,
    compute_deflated_sharpe_ratio,
    compute_classification_metrics,
    GaussianRegimeHMM,
    detect_regimes_hmm,
)

__all__ = [
    # Level 8
    "compute_capm_beta",
    "compute_capm_expected_return",
    "compute_capm",
    "compute_fama_french_3factor",
    "compute_sharpe_ratio",
    "compute_annualized_risk_adjusted_metrics",
    "compute_discrete_kelly",
    "compute_continuous_kelly",
    "compute_parametric_var",
    "compute_expected_shortfall",
    "compute_historical_var_cvar",
    "compute_max_drawdown",
    # Level 9
    "compute_mid_price",
    "compute_spreads",
    "compute_order_book_imbalance",
    "compute_multilevel_imbalance",
    "compute_microprice",
    "compute_square_root_impact",
    "compute_vwap",
    "compute_twap",
    "compute_implementation_shortfall",
    "compute_avellaneda_stoikov",
    # Level 10
    "audit_backtest_biases",
    "generate_walk_forward_windows",
    "compute_walk_forward_efficiency",
    "compute_deflated_sharpe_ratio",
    "compute_classification_metrics",
    "GaussianRegimeHMM",
    "detect_regimes_hmm",
]
