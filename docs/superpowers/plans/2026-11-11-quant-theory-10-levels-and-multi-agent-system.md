# 10-Level 50-Formula Quant Engine & Multi-Agent Deliberation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete 10-Level, 50-Formula Quantitative Mathematical Architecture ("The Entire Quant Theory on One Sheet" by @RitOnChain), integrate microstructure order flow (CVD, absorption), market making (Avellaneda-Stoikov), strategy protections (Freqtrade/NautilusTrader), and an asynchronous multi-agent hedge fund committee (Simons, Wood, Buffett, Risk Manager, Arbiter), verified with complete unit tests and terminal telemetry on `localhost:8900`.

**Architecture:** Two-tier hybrid architecture. Tier 1 is a low-latency, pure-math deterministic quantitative engine implementing all 50 formulas across Levels 1–10 with order flow and protections. Tier 2 is a decoupled asynchronous multi-agent deliberation service providing qualitative conviction scoring without blocking execution.

**Tech Stack:** Python 3.12, NumPy, SciPy (stats, optimize, linalg), native stdlib (math, statistics, typing, json, threading, urllib).

**Spec:** `docs/superpowers/specs/2026-11-11-quant-theory-10-levels-and-multi-agent-system.md`

## Global Constraints
- **Zero Lookahead:** All time-series signals and filters must operate strictly on past closed bars ($data \le t-1$) with execution on bar $t$.
- **Pure Numerical Functions:** Quant formulas must be deterministic pure functions with explicit zero-division guards and clean fallbacks.
- **Backward Compatibility:** All existing 469 tests (56 quant tests + 413 isolated tests) must continue to pass with zero regressions.
- **Execution Authority:** Only the 5-Gate Governor holds trading authorization; Tier 1 and Tier 2 outputs are purely analytical and advisory.

## Review Focus
1. **Empty/Degenerate Inputs:** Zero variance, empty trade streams, or division by zero in correlation, Sharpe, or GARCH calculations must return safe numerical fallbacks rather than crashing with `ZeroDivisionError`.
2. **Ill-Conditioned Covariance Matrices:** Covariance matrices with high condition numbers must be safely regularized via Ledoit-Wolf shrinkage prior to Markowitz inversion.
3. **Black-Scholes At-The-Money & Expiry Boundary:** $T \le 0$ or deep in/out-of-the-money options must not cause overflow in exponent or division by $\sqrt{T} \approx 0$.
4. **Order Book Depletion in Avellaneda-Stoikov:** When order books have zero liquidity, quoting must gracefully anchor to the last traded price.
5. **Decoupled Asynchronous Deliberation:** The multi-agent deliberation layer must never block the main dashboard thread or quant pipeline.

---

## Tasks

### Task 1: Levels 1 & 2 — Probability & Statistics Core (Formulas 1.1–1.5 & 2.1–2.5)

**Files:**
- Create: `core/quant/levels/level1_prob.py`
- Create: `core/quant/levels/level2_stats.py`
- Test: `tests/test_level1_prob.py`
- Test: `tests/test_level2_stats.py`

- [ ] Write failing tests for Level 1 (Bayes rule, linearity of expectation, variance, total expectation, distributions).
- [ ] Run `python -m pytest tests/test_level1_prob.py` to confirm test failure.
- [ ] Implement `level1_prob.py`:
  - `compute_bayes_update(prior_a, prob_b_given_a, prob_b_given_not_a) -> float`
  - `compute_linear_expectation(expectations: Sequence[float], weights: Sequence[float] | None = None) -> float`
  - `compute_sample_variance(values: Sequence[float]) -> float`
  - `compute_total_expectation(conditional_expectations: Sequence[float], probabilities: Sequence[float]) -> float`
  - `evaluate_distribution_density(dist_type: str, x: float, **kwargs) -> float`
- [ ] Write failing tests for Level 2 (Standard error, Sharpe t-stat, OLS regression, Correlation/$R^2$, Multiple testing).
- [ ] Run `python -m pytest tests/test_level2_stats.py` to confirm test failure.
- [ ] Implement `level2_stats.py`:
  - `compute_standard_error(std_dev: float, n: int) -> float`
  - `compute_sharpe_tstat(sharpe: float, years: float) -> float`
  - `compute_ols_regression(x: Sequence[float], y: Sequence[float]) -> dict[str, float]` (beta, alpha, r_squared, se)
  - `compute_correlation_and_r2(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]`
  - `compute_multiple_testing_p_false(alpha: float, n_tests: int) -> float`
- [ ] Run `python -m pytest tests/test_level1_prob.py tests/test_level2_stats.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 1 probability and level 2 statistics modules`

---

### Task 2: Levels 3 & 4 — Linear Algebra & Optimization Core (Formulas 3.1–3.5 & 4.1–4.5)

**Files:**
- Create: `core/quant/levels/level3_linalg.py`
- Create: `core/quant/levels/level4_opt.py`
- Test: `tests/test_level3_linalg.py`
- Test: `tests/test_level4_opt.py`

- [ ] Write failing tests for Level 3 (Covariance matrix, Portfolio variance, PCA/eigenvalues, Condition number, Ledoit-Wolf shrinkage).
- [ ] Run `python -m pytest tests/test_level3_linalg.py` to confirm failure.
- [ ] Implement `level3_linalg.py`:
  - `compute_covariance_matrix(returns_matrix: Sequence[Sequence[float]]) -> list[list[float]]`
  - `compute_portfolio_variance(weights: Sequence[float], cov_matrix: Sequence[Sequence[float]]) -> float`
  - `compute_pca_components(cov_matrix: Sequence[Sequence[float]]) -> dict[str, Any]` (eigenvalues, eigenvectors, variance_explained)
  - `compute_matrix_condition_number(matrix: Sequence[Sequence[float]]) -> float`
  - `compute_ledoit_wolf_shrinkage(returns_matrix: Sequence[Sequence[float]], shrinkage_target: str = "identity") -> list[list[float]]`
- [ ] Write failing tests for Level 4 (Taylor expansion Greeks, Gradient descent, Lagrange multipliers, Markowitz weights, Jensen's volatility drag).
- [ ] Run `python -m pytest tests/test_level4_opt.py` to confirm failure.
- [ ] Implement `level4_opt.py`:
  - `compute_taylor_pnl_approximation(delta: float, gamma: float, theta: float, delta_s: float, delta_t: float) -> float`
  - `run_gradient_descent_step(theta: Sequence[float], gradient: Sequence[float], learning_rate: float) -> list[float]`
  - `solve_lagrange_budget_allocation(utilities: Sequence[float], costs: Sequence[float], budget: float) -> list[float]`
  - `compute_markowitz_weights(expected_returns: Sequence[float], cov_matrix: Sequence[Sequence[float]], risk_aversion: float = 1.0) -> list[float]`
  - `compute_jensen_volatility_drag(mean_return: float, volatility: float) -> float`
- [ ] Run `python -m pytest tests/test_level3_linalg.py tests/test_level4_opt.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 3 linear algebra and level 4 optimization modules`

---

### Task 3: Levels 5 & 6 — Time Series & Stochastic Calculus (Formulas 5.1–5.5 & 6.1–6.5)

**Files:**
- Create: `core/quant/levels/level5_timeseries.py`
- Create: `core/quant/levels/level6_stoch.py`
- Test: `tests/test_level5_timeseries.py`
- Test: `tests/test_level6_stoch.py`

- [ ] Write failing tests for Level 5 (Log returns, Autocorrelation, ADF test, Cointegration & half-life, GARCH(1,1)).
- [ ] Run `python -m pytest tests/test_level5_timeseries.py` to confirm failure.
- [ ] Implement `level5_timeseries.py`:
  - `compute_log_returns(prices: Sequence[float]) -> list[float]`
  - `compute_autocorrelation(series: Sequence[float], lag: int = 1) -> float`
  - `compute_stationarity_adf(series: Sequence[float]) -> dict[str, float]`
  - `compute_cointegration_half_life(series_x: Sequence[float], series_y: Sequence[float]) -> dict[str, float]`
  - `compute_garch11_volatility(returns: Sequence[float], omega: float = 1e-6, alpha: float = 0.05, beta: float = 0.90) -> list[float]`
- [ ] Write failing tests for Level 6 (Random walk, Brownian motion, GBM simulation, Itô's lemma, Gambler's ruin).
- [ ] Run `python -m pytest tests/test_level6_stoch.py` to confirm failure.
- [ ] Implement `level6_stoch.py`:
  - `simulate_random_walk(n_steps: int, sigma: float = 1.0, seed: int = 42) -> list[float]`
  - `simulate_brownian_motion(n_steps: int, dt: float = 1.0, seed: int = 42) -> list[float]`
  - `simulate_gbm_paths(s0: float, mu: float, sigma: float, dt: float, n_steps: int, n_paths: int = 100, seed: int = 42) -> list[list[float]]`
  - `evaluate_ito_drift_diffusion(df_dt: float, df_ds: float, d2f_ds2: float, mu: float, sigma: float, s: float) -> tuple[float, float]`
  - `compute_gamblers_ruin(win_prob: float, units: int) -> float`
- [ ] Run `python -m pytest tests/test_level5_timeseries.py tests/test_level6_stoch.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 5 time series and level 6 stochastic calculus modules`

---

### Task 4: Level 7 — Derivatives & Greeks (Formulas 7.1–7.5)

**Files:**
- Create: `core/quant/levels/level7_derivatives.py`
- Test: `tests/test_level7_derivatives.py`

- [ ] Write failing tests for Level 7 (Black-Scholes call/put, Put-call parity, Greeks, Implied volatility solver, Gamma P&L).
- [ ] Run `python -m pytest tests/test_level7_derivatives.py` to confirm failure.
- [ ] Implement `level7_derivatives.py`:
  - `compute_black_scholes_price(s: float, k: float, t: float, r: float, sigma: float, is_call: bool = True) -> float`
  - `verify_put_call_parity(call_price: float, put_price: float, s: float, k: float, t: float, r: float) -> float`
  - `compute_option_greeks(s: float, k: float, t: float, r: float, sigma: float, is_call: bool = True) -> dict[str, float]` (delta, gamma, theta, vega, rho)
  - `solve_implied_volatility(market_price: float, s: float, k: float, t: float, r: float, is_call: bool = True) -> float`
  - `compute_gamma_pnl(gamma: float, theta: float, delta_s: float, delta_t: float) -> float`
- [ ] Run `python -m pytest tests/test_level7_derivatives.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 7 derivatives and option greeks module`

---

### Task 5: Level 8 — Portfolio & Risk (Formulas 8.1–8.5)

**Files:**
- Create: `core/quant/levels/level8_risk.py`
- Test: `tests/test_level8_risk.py`

- [ ] Write failing tests for Level 8 (CAPM beta & alpha, Fama-French 3-factor, Sharpe ratio, Kelly criterion, VaR / Expected Shortfall / Drawdown).
- [ ] Run `python -m pytest tests/test_level8_risk.py` to confirm failure.
- [ ] Implement `level8_risk.py`:
  - `compute_capm_alpha_beta(asset_returns: Sequence[float], market_returns: Sequence[float], rf: float = 0.0) -> tuple[float, float]`
  - `compute_fama_french_3factor(asset_returns: Sequence[float], mkt_excess: Sequence[float], smb: Sequence[float], hml: Sequence[float]) -> dict[str, float]`
  - `compute_sharpe_ratio(returns: Sequence[float], rf: float = 0.0, bars_per_year: float = 365.0) -> float`
  - `compute_kelly_criterion(win_prob: float, win_loss_ratio: float, fraction: float = 0.5) -> float`
  - `compute_continuous_kelly(mean_return: float, variance: float, rf: float = 0.0, fraction: float = 0.5) -> float`
  - `compute_var_es_drawdown(equity_curve: Sequence[float], daily_vol: float, confidence: float = 0.95) -> dict[str, float]`
- [ ] Run `python -m pytest tests/test_level8_risk.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 8 portfolio theory and risk metrics module`

---

### Task 6: Level 9 — Microstructure & Execution (Formulas 9.1–9.5)

**Files:**
- Create: `core/quant/levels/level9_microstructure.py`
- Test: `tests/test_level9_microstructure.py`

- [ ] Write failing tests for Level 9 (Spread & mid, Order book imbalance & microprice, Square-root impact, VWAP/TWAP & shortfall, Avellaneda-Stoikov market making).
- [ ] Run `python -m pytest tests/test_level9_microstructure.py` to confirm failure.
- [ ] Implement `level9_microstructure.py`:
  - `compute_spread_and_mid(bid: float, ask: float) -> tuple[float, float, float]` (mid, spread, half_spread)
  - `compute_microprice_and_imbalance(bid_p: float, bid_q: float, ask_p: float, ask_q: float, last_price: float | None = None) -> tuple[float, float]`
  - `compute_square_root_impact(volatility: float, order_qty: float, daily_volume: float, impact_constant: float = 1.0) -> float`
  - `compute_vwap_twap_shortfall(trades: Sequence[tuple[float, float]], decision_price: float) -> dict[str, float]`
  - `compute_avellaneda_stoikov(mid_price: float, inventory: float, gamma: float, sigma: float, time_horizon: float, kappa: float) -> dict[str, float]` (reservation_price, optimal_bid, optimal_ask, spread)
- [ ] Run `python -m pytest tests/test_level9_microstructure.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 9 microstructure and market making module`

---

### Task 7: Level 10 — Research, Validation & ML (Formulas 10.1–10.5)

**Files:**
- Create: `core/quant/levels/level10_research.py`
- Test: `tests/test_level10_research.py`

- [ ] Write failing tests for Level 10 (Backtest biases audit, Walk-forward validation, Deflated Sharpe Ratio [DSR], Precision/Recall/F1, Regime switch HMM).
- [ ] Run `python -m pytest tests/test_level10_research.py` to confirm failure.
- [ ] Implement `level10_research.py`:
  - `audit_backtest_integrity(trades: Sequence[dict[str, Any]], fills_at_open: bool = True, transaction_costs_included: bool = True) -> dict[str, Any]`
  - `generate_walk_forward_splits(n_samples: int, train_size: int, test_size: int) -> list[tuple[list[int], list[int]]]`
  - `compute_deflated_sharpe_ratio(observed_sharpe: float, n_trials: int, sample_length: int, skewness: float = 0.0, kurtosis: float = 3.0) -> float`
  - `compute_classification_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float]` (precision, recall, f1)
  - `detect_volatility_regime(returns: Sequence[float], window_short: int = 20, window_long: int = 100, threshold: float = 1.5) -> dict[str, Any]`
- [ ] Run `python -m pytest tests/test_level10_research.py` to verify all pass.
- [ ] Commit: `feat(quant): implement level 10 research validation and deflated sharpe module`

---

### Task 8: Microstructure, Order Flow & Protections Modules

**Files:**
- Create: `core/quant/microstructure/order_flow.py`
- Create: `core/quant/microstructure/market_making.py`
- Create: `core/quant/microstructure/protections.py`
- Create: `core/quant/factors/alpha158.py`
- Test: `tests/test_order_flow.py`
- Test: `tests/test_market_making.py`
- Test: `tests/test_protections.py`
- Test: `tests/test_alpha_factors.py`

- [ ] Write failing tests for Order Flow Engine (`compute_cvd_series`, `detect_delta_divergence`, `detect_absorption`).
- [ ] Implement `order_flow.py` (Cumulative Volume Delta, Delta Divergence, Absorption Detection).
- [ ] Write failing tests for Market Making Engine (`AvellanedaStoikovQuoter`, inventory-skewed quoting).
- [ ] Implement `market_making.py`.
- [ ] Write failing tests for Strategy Protections (`CooldownGuard`, `StoplossGuard`, `BracketOrderSimulator`).
- [ ] Implement `protections.py`.
- [ ] Write failing tests for Alpha Factor Engine (`compute_alpha_momentum`, `compute_alpha_volatility`, `compute_alpha_cross_ma`).
- [ ] Implement `alpha158.py`.
- [ ] Run all 4 new test files to verify they pass.
- [ ] Commit: `feat(quant): implement order flow CVD, market making quoter, and protection guards`

---

### Task 9: Backward Compatibility Layer & Pipeline Unification

**Files:**
- Modify: `core/quant/stage1_data.py`
- Modify: `core/quant/stage2_signal.py`
- Modify: `core/quant/stage3_filter.py`
- Modify: `core/quant/stage4_edge.py`
- Modify: `core/quant/stage5_size.py`
- Modify: `core/quant/stage6_execute.py`
- Modify: `core/quant/stage7_risk.py`
- Modify: `core/quant/stage8_validate.py`
- Modify: `core/quant/pipeline.py`
- Modify: `core/quant/__init__.py`
- Test: `tests/test_quant_pipeline.py`

- [ ] Wire existing stage modules to cleanly delegate to the new 10-level functions while maintaining identical signatures and backward compatibility.
- [ ] Enhance `QuantPipeline` to integrate Level 1–10 metrics and order flow CVD.
- [ ] Run `python -m pytest tests/test_stage*.py tests/test_quant_pipeline.py` to confirm all 56 existing quant tests pass.
- [ ] Commit: `refactor(quant): unify 8 stages with 10-level architecture with complete backwards compatibility`

---

### Task 10: Tier 2 Async Multi-Agent Hedge Fund Committee

**Files:**
- Create: `core/agents/hedge_fund_committee.py`
- Test: `tests/test_hedge_fund_committee.py`

- [ ] Write failing tests for `HedgeFundCommittee` (Simons, Wood, Buffett, Risk Officer, Arbiter consensus).
- [ ] Implement `hedge_fund_committee.py`:
  - `JimSimonsAgent`: Evaluates statistical stationarity, alpha factor z-scores, and Sharpe t-stat.
  - `CathieWoodAgent`: Evaluates volume surge, trend momentum, and growth signals.
  - `WarrenBuffettAgent`: Integrates with `BerkshireCommittee` for moat and valuation margin of safety.
  - `RiskOfficerAgent`: Enforces hard drawdown and VaR sizing limits with veto capability.
  - `PortfolioArbiter`: Synthesizes votes into final recommendation (`BUY`, `SELL`, `HOLD`), conviction score, and position weight.
  - Async non-blocking execution with caching to ensure fast turnaround.
- [ ] Run `python -m pytest tests/test_hedge_fund_committee.py` to verify all pass.
- [ ] Commit: `feat(agents): implement async multi-agent hedge fund committee with risk officer veto`

---

### Task 11: Terminal Dashboard Telemetry & Multi-Pane UI (`localhost:8900`)

**Files:**
- Modify: `cryptoscope/dashboard/__main__.py`
- Modify: `cryptoscope/dashboard/static/index.html`
- Modify: `cryptoscope/dashboard/static/app.js`
- Test: `tests/test_quant_extended_api.py`

- [ ] Add endpoints to `cryptoscope/dashboard/__main__.py`:
  - `GET /api/quant/levels` (returns 10-level 50-formula computed state)
  - `GET /api/quant/orderflow` (returns CVD and volume delta series)
  - `POST /api/agents/committee` (triggers multi-agent hedge fund deliberation with rate limiting)
- [ ] Update `cryptoscope/dashboard/static/index.html` with:
  - 10-Level 50-Formula matrix interactive tab
  - Order Flow CVD stream pane
  - Multi-Agent Hedge Fund Deliberation panel
- [ ] Update `cryptoscope/dashboard/static/app.js` with live polling and trigger controllers.
- [ ] Write and run `tests/test_quant_extended_api.py`.
- [ ] Commit: `feat(dashboard): add 10-level quant matrix, CVD order flow, and hedge fund committee UI`

---

### Task 12: Full System Regression Suite & Verification

**Files:**
- Run: `python -m pytest tests/ -v`
- Run: `python -B scripts/run_isolated_tests.py`

- [ ] Run all unit tests in `tests/` and confirm 100% pass rate.
- [ ] Run full isolated regression test runner (`scripts/run_isolated_tests.py`) and confirm all 413+ tests pass with zero regressions.
- [ ] Document final test evidence and verify dashboard status.
- [ ] Commit any remaining integration adjustments: `chore(release): finalize 10-level quant engine and multi-agent system integration`
