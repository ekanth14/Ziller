"""10-Level Quantitative Finance Theory Modules.

Levels 1-4: Math Core
- Level 1: Probability (Bayes, Linearity of Exp, Variance, Total Exp, Distributions)
- Level 2: Statistics (Standard Error, Sharpe t-stat, OLS, Correlation/R^2, Multiple Testing)
- Level 3: Linear Algebra (Covariance, Portfolio Variance, PCA, Matrix Conditioning, Ledoit-Wolf)
- Level 4: Calculus & Optimization (Taylor Expansion, Gradient Descent, Lagrange Multipliers, Markowitz, Jensen's Vol Drag)
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
]
