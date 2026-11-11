"""10-Level Quantitative Finance Theory Module.

Levels 1-10 covering 50 institutional formulas:
Level 1: Probability (1.1 - 1.5)
Level 2: Statistics (2.1 - 2.5)
Level 3: Linear Algebra (3.1 - 3.5)
Level 4: Calculus & Optimization (4.1 - 4.5)
Level 5: Time Series (5.1 - 5.5)
Level 6: Stochastic Calculus (6.1 - 6.5)
Level 7: Derivatives & Greeks (7.1 - 7.5)
Level 8: Portfolio & Risk (8.1 - 8.5)
Level 9: Microstructure & Execution (9.1 - 9.5)
Level 10: Research & Machine Learning (10.1 - 10.5)
"""

from core.quant.levels.level1_prob import (
    compute_bayes_update,
    compute_linear_expectation,
    compute_sample_variance,
    compute_variance_from_moments,
    compute_total_expectation,
    evaluate_distribution_density,
    evaluate_distribution_cdf,
)
from core.quant.levels.level2_stats import (
    compute_standard_error,
    compute_sharpe_t_stat,
    compute_univariate_hedge_ratio,
    compute_ols_regression,
    compute_correlation,
    compute_r_squared,
    compute_family_wise_error_rate,
    bonferroni_correction,
    benjamini_hochberg_fdr,
)
from core.quant.levels.level3_linalg import (
    compute_covariance_matrix,
    is_positive_semi_definite,
    ensure_positive_semi_definite,
    compute_portfolio_variance,
    compute_portfolio_volatility,
    compute_pca_factors,
    compute_condition_number,
    is_well_conditioned,
    safe_matrix_inverse,
    ledoit_wolf_shrinkage,
)
from core.quant.levels.level4_opt import (
    compute_taylor_expansion_1d,
    approximate_derivatives,
    taylor_pnl_approximation,
    gradient_descent,
    solve_lagrange_quadratic,
    solve_minimum_variance_portfolio,
    compute_markowitz_weights,
    compute_volatility_drag,
    check_jensen_inequality,
)
from core.quant.levels.level5_timeseries import (
    compute_log_returns,
    compute_annualized_volatility,
    compute_autocorrelation,
    classify_autocorrelation_regime,
    compute_adf_stationarity,
    compute_cointegration_hedge_ratio,
    compute_half_life,
    compute_garch11_filter,
    forecast_garch11_next,
    estimate_garch11_parameters,
)
from core.quant.levels.level6_stoch import (
    simulate_random_walk,
    compute_random_walk_variance,
    compute_diffusion_scaling,
    simulate_brownian_motion,
    simulate_gbm_path,
    gbm_expected_value,
    gbm_variance,
    compute_ito_drift,
    compute_ito_diffusion,
    ito_log_price_drift,
    compute_gamblers_ruin,
    compute_infinite_horizon_ruin,
    is_martingale_property,
)
from core.quant.levels.level7_derivatives import (
    black_scholes_call,
    black_scholes_put,
    black_scholes_price,
    verify_put_call_parity,
    compute_synthetic_price,
    compute_option_greeks,
    compute_implied_volatility,
    compute_gamma_pnl,
    compute_gamma_vol_arbitrage_pnl,
)
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
    # Level 1
    "compute_bayes_update",
    "compute_linear_expectation",
    "compute_sample_variance",
    "compute_variance_from_moments",
    "compute_total_expectation",
    "evaluate_distribution_density",
    "evaluate_distribution_cdf",
    # Level 2
    "compute_standard_error",
    "compute_sharpe_t_stat",
    "compute_univariate_hedge_ratio",
    "compute_ols_regression",
    "compute_correlation",
    "compute_r_squared",
    "compute_family_wise_error_rate",
    "bonferroni_correction",
    "benjamini_hochberg_fdr",
    # Level 3
    "compute_covariance_matrix",
    "is_positive_semi_definite",
    "ensure_positive_semi_definite",
    "compute_portfolio_variance",
    "compute_portfolio_volatility",
    "compute_pca_factors",
    "compute_condition_number",
    "is_well_conditioned",
    "safe_matrix_inverse",
    "ledoit_wolf_shrinkage",
    # Level 4
    "compute_taylor_expansion_1d",
    "approximate_derivatives",
    "taylor_pnl_approximation",
    "gradient_descent",
    "solve_lagrange_quadratic",
    "solve_minimum_variance_portfolio",
    "compute_markowitz_weights",
    "compute_volatility_drag",
    "check_jensen_inequality",
    # Level 5
    "compute_log_returns",
    "compute_annualized_volatility",
    "compute_autocorrelation",
    "classify_autocorrelation_regime",
    "compute_adf_stationarity",
    "compute_cointegration_hedge_ratio",
    "compute_half_life",
    "compute_garch11_filter",
    "forecast_garch11_next",
    "estimate_garch11_parameters",
    # Level 6
    "simulate_random_walk",
    "compute_random_walk_variance",
    "compute_diffusion_scaling",
    "simulate_brownian_motion",
    "simulate_gbm_path",
    "gbm_expected_value",
    "gbm_variance",
    "compute_ito_drift",
    "compute_ito_diffusion",
    "ito_log_price_drift",
    "compute_gamblers_ruin",
    "compute_infinite_horizon_ruin",
    "is_martingale_property",
    # Level 7
    "black_scholes_call",
    "black_scholes_put",
    "black_scholes_price",
    "verify_put_call_parity",
    "compute_synthetic_price",
    "compute_option_greeks",
    "compute_implied_volatility",
    "compute_gamma_pnl",
    "compute_gamma_vol_arbitrage_pnl",
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
