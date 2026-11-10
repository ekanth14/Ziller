# Institutional Quant Trading Engine & Bloomberg-Style Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify an institutional-grade, mathematically complete quantitative trading pipeline consisting of 8 sequential stages and 48 deterministic formulas (inspired by JPMorgan, Bloomberg, Fincept, and AI Berkshire), integrated with an interactive terminal interface on `http://localhost:8900`.

**Architecture:** A decoupled, deterministic Python quantitative computing package (`core/quant/`) containing pure functions with zero lookahead bias and Decimal/NumPy numerical rigor. Real-time metrics (Stages 1–3, 5–7) execute in sub-millisecond streaming mode per bar/tick; trade expectancy (Stage 4) and Monte Carlo / walk-forward splits (Stage 8) execute asynchronously. An interactive Bloomberg/Fincept-style terminal workstation exposes live market depth, microprice, 48-formula telemetry, and an on-demand AI Berkshire qualitative research panel on `localhost:8900`.

**Tech Stack:** Python 3.12, NumPy, SciPy, Pandas, FastAPI, SSE (Server-Sent Events), TradingView Lightweight Charts v4.2.1, SQLite WAL, Pytest.

**Spec:** [docs/superpowers/specs/2026-11-09-quant-pipeline-and-terminal-design.md](file:///c:/Users/Ekanth's%20laptop/Desktop/my%20projects/zien-crypto/docs/superpowers/specs/2026-11-09-quant-pipeline-and-terminal-design.md)

## Global Constraints
* **Trading Authorization**: `trading_authorized = false` remains strictly enforced unless explicit human authorization is provided.
* **Pure Analytical Authority**: Stages 6 and 7 calculate analytical metrics and trigger advisory flags; the existing 5-Gate Governor retains exclusive authority over process halts.
* **Zero Lookahead Rule**: Signals are calculated only on closed bars ($t \le -1$). Simulated or benchmark fills happen on bar open ($t$).
* **Deterministic Math**: Pure functions using Python `math`, `decimal.Decimal`, or `numpy` for verifiable calculations without LLM hallucinations.
* **Test Preservation**: All existing 413 unit/integration tests must continue to pass with 0 regressions.

## Review Focus
1. **Division by Zero in Low Volatility**: Price series with constant prices ($\sigma = 0$) must return well-defined fallbacks ($z = 0$, $\text{size} = 0$, $w = 0$) rather than raising `ZeroDivisionError` or `NaN`.
2. **Log Return of Non-Positive Prices**: Invalid or zero prices ($P_t \le 0$) must be rejected by the data clean stage with explicit error handling.
3. **Empty or Single-Item Series**: Statistical functions ($t$-stat, ADF, Hurst, Sharpe) must handle sample sizes $n < 2$ safely by returning `None` or neutral scores without crashing.
4. **Order Book Depletion**: Zero bid/ask liquidity in imbalance or microprice formulas must gracefully fall back to last traded price rather than crashing.
5. **Monte Carlo Streak Preservation**: Trade shuffle validation must handle 100% win or 100% loss trade series without divergence.

---

### Task 1: Stage 1 Data Clean Engine (Formulas 1.1–1.6)

**Files:**
- Create: `core/quant/stage1_data.py`
- Test: `tests/test_stage1_data.py`

**Interfaces:**
- Consumes: Raw price/candle sequences: `timestamps`, `opens`, `highs`, `lows`, `closes`, `volumes`.
- Produces:
  - `compute_log_returns(prices: list[float]) -> list[float]`
  - `compute_annualized_vol(returns: list[float], bars_per_year: int = 365) -> float`
  - `compute_ewma_vol(returns: list[float], lambda_param: float = 0.94) -> list[float]`
  - `compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]`
  - `filter_bad_ticks(returns: list[float], threshold_sigma: float = 6.0) -> list[bool]`
  - `verify_no_lookahead(bar_index: int, signal_time: int, fill_time: int) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage1_data.py
import math
import pytest
from core.quant.stage1_data import (
    compute_log_returns,
    compute_annualized_vol,
    compute_ewma_vol,
    compute_atr,
    filter_bad_ticks,
    verify_no_lookahead,
)

def test_log_returns_additive():
    prices = [100.0, 110.0, 100.0]
    r = compute_log_returns(prices)
    assert len(r) == 2
    assert math.isclose(r[0], math.log(1.10), rel_tol=1e-5)
    assert math.isclose(r[1], math.log(100.0 / 110.0), rel_tol=1e-5)
    assert math.isclose(sum(r), 0.0, abs_tol=1e-7)

def test_annualized_vol_crypto_365():
    # 1% daily volatility over 365 days
    daily_vol = 0.01
    annual_vol = compute_annualized_vol([daily_vol] * 365, bars_per_year=365)
    assert math.isclose(annual_vol, daily_vol * math.sqrt(365), rel_tol=1e-4)

def test_ewma_vol_shock():
    # shock jump with lambda=0.94
    returns = [0.02, -0.05]
    vols = compute_ewma_vol(returns, lambda_param=0.94)
    assert len(vols) == 2
    assert vols[1] > vols[0]

def test_atr_with_gaps():
    highs = [105.0]
    lows = [101.0]
    closes = [99.0] # previous close 99 -> TR = max(4, |105-99|, |101-99|) = 6
    # 2 bars to test previous close
    atr = compute_atr(highs=[100.0, 105.0], lows=[98.0, 101.0], closes=[99.0, 104.0], period=1)
    assert atr[-1] == 6.0

def test_bad_tick_filter():
    returns = [0.001, -0.002, 0.001, -0.001, 0.09] # 0.09 is ~9% jump > 6 sigma
    flags = filter_bad_ticks(returns, threshold_sigma=6.0)
    assert flags[-1] is True
    assert flags[0] is False

def test_no_lookahead_validator():
    # Signal on close of bar t (100), fill on open of bar t+1 (101)
    assert verify_no_lookahead(bar_index=100, signal_time=100, fill_time=101) is True
    assert verify_no_lookahead(bar_index=100, signal_time=100, fill_time=100) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage1_data.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.quant'"

- [ ] **Step 3: Implement Stage 1 pure functions in `core/quant/stage1_data.py`**

Implement `compute_log_returns`, `compute_annualized_vol`, `compute_ewma_vol`, `compute_atr`, `filter_bad_ticks`, and `verify_no_lookahead` using standard math/NumPy. Ensure zero-division and empty-array guards.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage1_data.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage1_data.py tests/test_stage1_data.py
git commit -m "feat(quant): implement stage 1 data cleaning engine (formulas 1.1-1.6)"
```

---

### Task 2: Stage 2 Signal Engine (Formulas 2.1–2.6)

**Files:**
- Create: `core/quant/stage2_signal.py`
- Test: `tests/test_stage2_signal.py`

**Interfaces:**
- Consumes: Cleaned price and order-book data from Stage 1.
- Produces:
  - `compute_zscore(values: list[float], window: int = 20) -> list[float]`
  - `compute_ema(values: list[float], period: int = 20) -> list[float]`
  - `compute_momentum_12_1(prices: list[float], lag_short: int = 21, lag_long: int = 252) -> float`
  - `compute_rsi(prices: list[float], period: int = 14) -> list[float]`
  - `compute_order_book_imbalance(bid_qty: float, ask_qty: float) -> float`
  - `compute_funding_carry_apr(funding_rate_8h: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage2_signal.py
import pytest
from core.quant.stage2_signal import (
    compute_zscore,
    compute_ema,
    compute_momentum_12_1,
    compute_rsi,
    compute_order_book_imbalance,
    compute_funding_carry_apr,
)

def test_zscore_calculation():
    # price 109, mean 100, std 4 -> z = (109-100)/4 = 2.25
    vals = [100.0] * 19 + [109.0]
    z = compute_zscore(vals, window=20)
    assert len(z) == len(vals)

def test_ema_alpha():
    # n=20 -> alpha = 2/(21) ≈ 0.095238
    vals = [10.0] * 20 + [20.0]
    ema = compute_ema(vals, period=20)
    assert ema[0] == 10.0
    assert ema[-1] > 10.0

def test_momentum_12_1():
    # 120 a month ago, 100 a year ago: 120/100 - 1 = +20%
    prices = [100.0] * 231 + [120.0] * 21
    mom = compute_momentum_12_1(prices, lag_short=21, lag_long=252)
    assert pytest.approx(mom, 0.01) == 0.20

def test_rsi_bounds():
    # 15 rising prices -> RSI should be high (>70)
    prices = [100.0 + i for i in range(30)]
    rsi = compute_rsi(prices, period=14)
    assert rsi[-1] > 70.0

def test_order_book_imbalance():
    # 900 on bid, 300 on ask: (900-300)/(900+300) = 600/1200 = 0.5
    imb = compute_order_book_imbalance(bid_qty=900.0, ask_qty=300.0)
    assert pytest.approx(imb, 1e-4) == 0.5

def test_funding_carry_apr():
    # 0.01% per 8h -> 0.0001 * 3 * 365 = 10.95%
    apr = compute_funding_carry_apr(funding_rate_8h=0.0001)
    assert pytest.approx(apr, 1e-4) == 0.1095
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage2_signal.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.quant.stage2_signal'"

- [ ] **Step 3: Implement Stage 2 functions in `core/quant/stage2_signal.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage2_signal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage2_signal.py tests/test_stage2_signal.py
git commit -m "feat(quant): implement stage 2 signal engine (formulas 2.1-2.6)"
```

---

### Task 3: Stage 3 Filter Engine (Formulas 3.1–3.6)

**Files:**
- Create: `core/quant/stage3_filter.py`
- Test: `tests/test_stage3_filter.py`

**Interfaces:**
- Consumes: Return streams and price series from Stages 1 & 2.
- Produces:
  - `compute_tstat_returns(returns: list[float]) -> float`
  - `compute_adf_test(series: list[float]) -> tuple[float, bool]` (stat, is_stationary_at_5pct)
  - `compute_half_life(series: list[float]) -> float`
  - `compute_hurst_exponent(series: list[float]) -> float`
  - `compute_correlation_matrix(series_dict: dict[str, list[float]]) -> dict[tuple[str, str], float]`
  - `is_high_vol_regime(short_vol: float, long_vol: float, threshold: float = 1.5) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage3_filter.py
import pytest
from core.quant.stage3_filter import (
    compute_tstat_returns,
    compute_adf_test,
    compute_half_life,
    compute_hurst_exponent,
    compute_correlation_matrix,
    is_high_vol_regime,
)

def test_tstat_returns_formula():
    # Mean 0.1%/day, sigma 2%, 400 days: t = 0.001 / (0.02 / 20) = 1.0
    # Simulate a return series with exact mean and sigma
    returns = [0.001] * 400
    # Add alternating noise to produce sigma=0.02
    for i in range(400):
        returns[i] += (0.02 if i % 2 == 0 else -0.02)
    t = compute_tstat_returns(returns)
    assert pytest.approx(t, 0.1) == 1.0

def test_half_life_mean_reversion():
    # OU process simulation or known lambda: half_life = -ln(2) / lambda
    # For lambda = -0.05, half_life ≈ 13.86
    # We test with synthetic mean-reverting series
    series = [100.0]
    for i in range(100):
        series.append(series[-1] - 0.05 * (series[-1] - 100.0) + (1.0 if i % 2 == 0 else -1.0))
    hl = compute_half_life(series)
    assert hl > 0.0

def test_hurst_exponent():
    # Random walk H ~ 0.5; trending H > 0.5
    trending = [float(i) for i in range(200)]
    h = compute_hurst_exponent(trending)
    assert h > 0.6

def test_high_vol_regime_switch():
    # sigma_20 60%, sigma_252 35% -> ratio = 1.71 > 1.5 -> True
    assert is_high_vol_regime(short_vol=0.60, long_vol=0.35, threshold=1.5) is True
    assert is_high_vol_regime(short_vol=0.30, long_vol=0.35, threshold=1.5) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage3_filter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 3 filter functions in `core/quant/stage3_filter.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage3_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage3_filter.py tests/test_stage3_filter.py
git commit -m "feat(quant): implement stage 3 filter engine (formulas 3.1-3.6)"
```

---

### Task 4: Stage 4 Edge Engine (Formulas 4.1–4.6)

**Files:**
- Create: `core/quant/stage4_edge.py`
- Test: `tests/test_stage4_edge.py`

**Interfaces:**
- Consumes: Historical trade log outcomes ($W$, $L$, win rate $p$, fees, slippage).
- Produces:
  - `compute_expected_value(win_prob: float, avg_win: float, avg_loss: float) -> float`
  - `compute_breakeven_win_rate(avg_win: float, avg_loss: float) -> float`
  - `compute_expectancy_in_r(win_prob: float, r_win: float) -> float`
  - `compute_profit_factor(gross_wins: float, gross_losses: float) -> float`
  - `compute_bayesian_win_rate(wins: int, n: int, alpha: float = 1.0, beta: float = 1.0) -> float`
  - `compute_net_edge(gross_edge: float, fee_rate: float, slippage_rate: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage4_edge.py
import pytest
from core.quant.stage4_edge import (
    compute_expected_value,
    compute_breakeven_win_rate,
    compute_expectancy_in_r,
    compute_profit_factor,
    compute_bayesian_win_rate,
    compute_net_edge,
)

def test_expected_value():
    # 40% win, $300 win, $150 loss: 0.4*300 - 0.6*150 = 120 - 90 = +$30
    ev = compute_expected_value(win_prob=0.4, avg_win=300.0, avg_loss=150.0)
    assert pytest.approx(ev, 1e-4) == 30.0

def test_breakeven_win_rate():
    # Win 2R, lose 1R (W/L = 2): 1/(1+2) = 33.3%
    be = compute_breakeven_win_rate(avg_win=200.0, avg_loss=100.0)
    assert pytest.approx(be, 1e-4) == 1.0 / 3.0

def test_expectancy_in_r():
    # 40% win at 3R: 0.4 * 3 - 0.6 * 1 = 1.2 - 0.6 = +0.6R
    exp_r = compute_expectancy_in_r(win_prob=0.4, r_win=3.0)
    assert pytest.approx(exp_r, 1e-4) == 0.6

def test_profit_factor():
    # $6,000 won, $4,000 lost: PF = 1.5
    pf = compute_profit_factor(gross_wins=6000.0, gross_losses=4000.0)
    assert pytest.approx(pf, 1e-4) == 1.5

def test_bayesian_win_rate():
    # Prior Beta(1,1), 7 wins in 10: (1+7)/(1+1+10) = 8/12 = 66.7%
    p_hat = compute_bayesian_win_rate(wins=7, n=10, alpha=1.0, beta=1.0)
    assert pytest.approx(p_hat, 1e-4) == 8.0 / 12.0

def test_net_edge():
    # 0.25% gross, 0.1% fee + 0.05% slip: net = 0.0025 - 2*(0.0010 + 0.0005) = -0.05%
    net = compute_net_edge(gross_edge=0.0025, fee_rate=0.0010, slippage_rate=0.0005)
    assert pytest.approx(net, 1e-5) == -0.0005
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage4_edge.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 4 edge functions in `core/quant/stage4_edge.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage4_edge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage4_edge.py tests/test_stage4_edge.py
git commit -m "feat(quant): implement stage 4 edge evaluation engine (formulas 4.1-4.6)"
```

---

### Task 5: Stage 5 Size Engine (Formulas 5.1–5.6)

**Files:**
- Create: `core/quant/stage5_size.py`
- Test: `tests/test_stage5_size.py`

**Interfaces:**
- Consumes: Equity, risk parameters, volatility, payoff ratio.
- Produces:
  - `compute_risk_based_size(equity: float, risk_pct: float, entry: float, stop: float) -> float`
  - `compute_kelly_criterion(win_prob: float, payoff_b: float, fraction: float = 0.5) -> float`
  - `compute_continuous_kelly(mean_return: float, var_return: float, fraction: float = 0.5) -> float`
  - `compute_volatility_target_weight(target_vol: float, realized_vol: float, max_leverage: float = 3.0) -> float`
  - `compute_risk_parity_weights(volatilities: dict[str, float]) -> dict[str, float]`
  - `compute_liquidation_price(entry: float, leverage: float, mmr: float = 0.005) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage5_size.py
import pytest
from core.quant.stage5_size import (
    compute_risk_based_size,
    compute_kelly_criterion,
    compute_continuous_kelly,
    compute_volatility_target_weight,
    compute_risk_parity_weights,
    compute_liquidation_price,
)

def test_risk_based_size():
    # $10k equity, 1% risk ($100), entry 100, stop 95: size = 100 / 5 = 20 units
    size = compute_risk_based_size(equity=10000.0, risk_pct=0.01, entry=100.0, stop=95.0)
    assert pytest.approx(size, 1e-4) == 20.0

def test_kelly_criterion_half():
    # p 0.55, b 1: f* = 0.55 - 0.45/1 = 0.10 (10%), half Kelly = 5%
    f_half = compute_kelly_criterion(win_prob=0.55, payoff_b=1.0, fraction=0.5)
    assert pytest.approx(f_half, 1e-4) == 0.05

def test_continuous_kelly():
    # mu 10%, sigma 20% (sigma^2 = 0.04): f* = 0.10 / 0.04 = 2.5x, half = 1.25x
    lev = compute_continuous_kelly(mean_return=0.10, var_return=0.04, fraction=0.5)
    assert pytest.approx(lev, 1e-4) == 1.25

def test_vol_target_cap():
    # Target 15%, asset 45%: weight = 15/45 = 1/3 ≈ 0.333
    w = compute_volatility_target_weight(target_vol=0.15, realized_vol=0.45, max_leverage=3.0)
    assert pytest.approx(w, 1e-4) == 1.0 / 3.0

def test_risk_parity_weights():
    # Assets with sigma 10% and 40%: weights 80% / 20%
    w = compute_risk_parity_weights({"A": 0.10, "B": 0.40})
    assert pytest.approx(w["A"], 1e-4) == 0.80
    assert pytest.approx(w["B"], 1e-4) == 0.20

def test_liquidation_price():
    # Entry 100, 10x leverage, mmr 0.5%: 100 * (1 - 1/10 + 0.005) = 100 * (0.905) = 90.5 (-9.5%)
    liq = compute_liquidation_price(entry=100.0, leverage=10.0, mmr=0.005)
    assert pytest.approx(liq, 1e-4) == 90.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage5_size.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 5 size functions in `core/quant/stage5_size.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage5_size.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage5_size.py tests/test_stage5_size.py
git commit -m "feat(quant): implement stage 5 position sizing engine (formulas 5.1-5.6)"
```

---

### Task 6: Stage 6 Execute Engine (Formulas 6.1–6.6)

**Files:**
- Create: `core/quant/stage6_execute.py`
- Test: `tests/test_stage6_execute.py`

**Interfaces:**
- Consumes: Bids, asks, execution fills, market daily volume, trading fees.
- Produces:
  - `compute_spread_cost(bid: float, ask: float) -> tuple[float, float]` (spread, half_spread_per_side)
  - `compute_microprice(bid_price: float, bid_qty: float, ask_price: float, ask_qty: float) -> float`
  - `compute_square_root_impact(volatility: float, order_qty: float, daily_volume: float) -> float`
  - `compute_vwap(trades: list[tuple[float, float]]) -> float`
  - `compute_slippage(expected_price: float, filled_price: float) -> float`
  - `compute_round_trip_fee(fee_rate: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage6_execute.py
import pytest
from core.quant.stage6_execute import (
    compute_spread_cost,
    compute_microprice,
    compute_square_root_impact,
    compute_vwap,
    compute_slippage,
    compute_round_trip_fee,
)

def test_spread_cost():
    # 99.95 / 100.05 -> mid 100.0, spread 0.10 (0.1%), half 0.05%
    spread, half = compute_spread_cost(bid=99.95, ask=100.05)
    assert pytest.approx(spread, 1e-4) == 0.001
    assert pytest.approx(half, 1e-4) == 0.0005

def test_microprice():
    # 100.00 x 900 bid, 100.10 x 300 ask -> (100*300 + 100.1*900)/1200 = 100.075
    p_micro = compute_microprice(bid_price=100.0, bid_qty=900.0, ask_price=100.10, ask_qty=300.0)
    assert pytest.approx(p_micro, 1e-4) == 100.075

def test_square_root_impact():
    # sigma 2%, order size 1% of daily volume: impact ≈ 0.02 * sqrt(0.01) = 0.02 * 0.1 = 0.002 (0.2%)
    impact = compute_square_root_impact(volatility=0.02, order_qty=100.0, daily_volume=10000.0)
    assert pytest.approx(impact, 1e-4) == 0.002

def test_vwap():
    # 100 @ 10.0, 200 @ 10.5 -> total = 1000 + 2100 = 3100 / 300 = 10.3333
    vwap = compute_vwap([(10.0, 100.0), (10.5, 200.0)])
    assert pytest.approx(vwap, 1e-4) == 10.3333

def test_slippage():
    # Expected 100, filled 100.08: 0.08%
    slip = compute_slippage(expected_price=100.0, filled_price=100.08)
    assert pytest.approx(slip, 1e-5) == 0.0008

def test_maker_taker_fee():
    # Taker 0.05% -> round trip = 0.10%
    assert pytest.approx(compute_round_trip_fee(0.0005), 1e-5) == 0.0010
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage6_execute.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 6 execute functions in `core/quant/stage6_execute.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage6_execute.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage6_execute.py tests/test_stage6_execute.py
git commit -m "feat(quant): implement stage 6 execution analysis engine (formulas 6.1-6.6)"
```

---

### Task 7: Stage 7 Risk Engine (Formulas 7.1–7.6)

**Files:**
- Create: `core/quant/stage7_risk.py`
- Test: `tests/test_stage7_risk.py`

**Interfaces:**
- Consumes: Equity series, portfolio weights, covariance matrix.
- Produces:
  - `compute_max_drawdown(equity_series: list[float]) -> tuple[float, float, float]` (dd_pct, peak, trough)
  - `compute_recovery_gain(drawdown_pct: float) -> float`
  - `compute_var_95(portfolio_value: float, daily_vol: float) -> float`
  - `compute_portfolio_volatility(weights: list[float], cov_matrix: list[list[float]]) -> float`
  - `compute_risk_of_ruin(win_prob: float, units: int) -> float`
  - `check_kill_switch(current_equity: float, peak_equity: float, max_allowed_dd: float = 0.15) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage7_risk.py
import pytest
from core.quant.stage7_risk import (
    compute_max_drawdown,
    compute_recovery_gain,
    compute_var_95,
    compute_portfolio_volatility,
    compute_risk_of_ruin,
    check_kill_switch,
)

def test_max_drawdown():
    # Peak $12k, low $9k: DD = 3k/12k = 25%
    series = [10000.0, 12000.0, 11000.0, 9000.0, 10500.0]
    dd, peak, trough = compute_max_drawdown(series)
    assert pytest.approx(dd, 1e-4) == 0.25
    assert peak == 12000.0
    assert trough == 9000.0

def test_recovery_math():
    # -20% needs +25%; -50% needs +100%
    assert pytest.approx(compute_recovery_gain(0.20), 1e-4) == 0.25
    assert pytest.approx(compute_recovery_gain(0.50), 1e-4) == 1.00

def test_var_95():
    # $10k at 3% daily sigma: 1.645 * 0.03 * 10000 = $493.5
    var = compute_var_95(portfolio_value=10000.0, daily_vol=0.03)
    assert pytest.approx(var, 0.5) == 493.5

def test_portfolio_volatility_two_assets():
    # 50/50, both 20% vol, rho 0.5: sigma_p = sqrt(0.5^2*0.04 + 0.5^2*0.04 + 2*0.5*0.5*0.04*0.5) = sqrt(0.01+0.01+0.01) = sqrt(0.03) ≈ 17.32%
    weights = [0.5, 0.5]
    cov = [[0.04, 0.02], [0.02, 0.04]]
    port_vol = compute_portfolio_volatility(weights, cov)
    assert pytest.approx(port_vol, 1e-3) == 0.1732

def test_risk_of_ruin():
    # p 0.55, N 20: ((1-0.55)/0.55)^20 = (0.45/0.55)^20 = (0.8181)^20 ≈ 1.84%
    ruin = compute_risk_of_ruin(win_prob=0.55, units=20)
    assert pytest.approx(ruin, 1e-3) == 0.0184

def test_kill_switch_trip():
    # Peak $10k, max DD 15%: stop under $8,500
    assert check_kill_switch(current_equity=8400.0, peak_equity=10000.0, max_allowed_dd=0.15) is True
    assert check_kill_switch(current_equity=8600.0, peak_equity=10000.0, max_allowed_dd=0.15) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage7_risk.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 7 risk functions in `core/quant/stage7_risk.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage7_risk.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage7_risk.py tests/test_stage7_risk.py
git commit -m "feat(quant): implement stage 7 risk and kill-switch engine (formulas 7.1-7.6)"
```

---

### Task 8: Stage 8 Validate Engine (Formulas 8.1–8.6)

**Files:**
- Create: `core/quant/stage8_validate.py`
- Test: `tests/test_stage8_validate.py`

**Interfaces:**
- Consumes: Return streams, trade records, strategy search parameters.
- Produces:
  - `compute_sharpe_ratio(returns: list[float], rf: float = 0.0, bars_per_year: int = 365) -> float`
  - `compute_sharpe_tstat(sharpe: float, years: float) -> float`
  - `compute_multiple_testing_p_false(alpha: float, n_tests: int) -> float`
  - `compute_best_of_n_noise_expected_sharpe(n_tests: int, sigma_sharpe: float = 0.5) -> float`
  - `generate_walk_forward_windows(total_bars: int, train_bars: int, test_bars: int) -> list[tuple[slice, slice]]`
  - `run_monte_carlo_drawdown(trade_pnls: list[float], iterations: int = 1000, confidence: float = 0.95) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage8_validate.py
import pytest
from core.quant.stage8_validate import (
    compute_sharpe_ratio,
    compute_sharpe_tstat,
    compute_multiple_testing_p_false,
    compute_best_of_n_noise_expected_sharpe,
    generate_walk_forward_windows,
    run_monte_carlo_drawdown,
)

def test_sharpe_tstat():
    # SR 1.0 over 4 years: t = 1.0 * sqrt(4) = 2.0
    t = compute_sharpe_tstat(sharpe=1.0, years=4.0)
    assert pytest.approx(t, 1e-4) == 2.0

def test_multiple_testing_p_false():
    # 20 tests at alpha=0.05: 1 - (1-0.05)^20 = 1 - 0.95^20 ≈ 64.15%
    p_false = compute_multiple_testing_p_false(alpha=0.05, n_tests=20)
    assert pytest.approx(p_false, 1e-3) == 0.6415

def test_best_of_n_noise():
    # Expected max SR from pure noise for N trials
    noise_sr = compute_best_of_n_noise_expected_sharpe(n_tests=1000, sigma_sharpe=0.5)
    assert noise_sr > 1.5

def test_walk_forward_splits():
    splits = generate_walk_forward_windows(total_bars=1000, train_bars=600, test_bars=200)
    assert len(splits) >= 2
    # Check non-overlapping test windows
    train1, test1 = splits[0]
    train2, test2 = splits[1]
    assert test1.stop <= test2.start

def test_monte_carlo_drawdown_shuffling():
    # 100 trades with some wins and losses
    pnls = [100.0, -80.0, 120.0, -50.0, 90.0, -110.0] * 20
    mc_dd = run_monte_carlo_drawdown(pnls, iterations=500, confidence=0.95)
    assert mc_dd > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage8_validate.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Stage 8 validation functions in `core/quant/stage8_validate.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage8_validate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/stage8_validate.py tests/test_stage8_validate.py
git commit -m "feat(quant): implement stage 8 validation and Monte Carlo engine (formulas 8.1-8.6)"
```

---

### Task 9: Quant Pipeline Orchestrator & Portfolio Coordinator

**Files:**
- Create: `core/quant/pipeline.py`
- Create: `core/quant/__init__.py`
- Test: `tests/test_quant_pipeline.py`

**Interfaces:**
- Consumes: Stage 1 through Stage 8 modules.
- Produces:
  - `class QuantPipeline`: Single-asset streaming pipeline running Stages 1–3, 5–7 per bar.
  - `class PortfolioCoordinator`: Joint multi-asset coordinator computing correlations, risk parity, and portfolio VaR.
  - `run_offline_validation(trades: list[float]) -> dict`: Asynchronous runner for Stages 4 & 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quant_pipeline.py
import pytest
from core.quant.pipeline import QuantPipeline, PortfolioCoordinator

def test_pipeline_streaming_bar():
    pipeline = QuantPipeline(symbol="BTCUSDT")
    # Feed 30 synthetic bars
    for i in range(30):
        metrics = pipeline.on_bar(
            open_p=100.0 + i,
            high_p=105.0 + i,
            low_p=98.0 + i,
            close_p=102.0 + i,
            volume=1000.0,
            bid_p=101.9,
            bid_q=50.0,
            ask_p=102.1,
            ask_q=40.0,
        )
    assert "log_return" in metrics
    assert "ewma_vol" in metrics
    assert "atr" in metrics
    assert "z_score" in metrics
    assert "microprice" in metrics
    assert "is_high_vol" in metrics

def test_portfolio_coordinator():
    coord = PortfolioCoordinator(symbols=["BTCUSDT", "ETHUSDT"])
    coord.update_price("BTCUSDT", [100.0 + i for i in range(25)])
    coord.update_price("ETHUSDT", [50.0 + (i*0.5) for i in range(25)])
    summary = coord.compute_portfolio_summary()
    assert "correlation" in summary
    assert "risk_parity_weights" in summary
    assert "portfolio_volatility" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quant_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `QuantPipeline` and `PortfolioCoordinator` in `core/quant/pipeline.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_quant_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/pipeline.py core/quant/__init__.py tests/test_quant_pipeline.py
git commit -m "feat(quant): integrate 8-stage quant pipeline and multi-asset portfolio coordinator"
```

---

### Task 10: AI Berkshire Committee Research Module

**Files:**
- Create: `core/quant/berkshire_committee.py`
- Test: `tests/test_berkshire_committee.py`

**Interfaces:**
- Consumes: Asset symbol, market cap, volume, cash flow / staking yield estimates.
- Produces:
  - `class BerkshireCommittee`:
    - `audit_asset(symbol: str, fundamental_data: dict) -> dict`
    - Evaluates:
      - `duan_moat`: Economic moat, user lock-in, fee generation (Duan Yongping).
      - `buffett_valuation`: Intrinsic value proxy, cash-yield sustainability (Warren Buffett).
      - `munger_inversion`: Reflexive leverage, failure modes, lollapalooza risks (Charlie Munger).
      - `lilu_integrity`: Governance, developer centralization, regulatory risk (Li Lu).
      - `rigor_check`: Deterministic `Decimal` validation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_berkshire_committee.py
import pytest
from core.quant.berkshire_committee import BerkshireCommittee

def test_berkshire_committee_evaluation():
    committee = BerkshireCommittee()
    data = {
        "market_cap": 1200000000000,
        "daily_volume": 35000000000,
        "staking_yield_pct": 0.0,
        "active_addresses": 950000,
        "hashrate_eh": 650.0,
    }
    report = committee.audit_asset("BTCUSDT", data)
    assert report["symbol"] == "BTCUSDT"
    assert "duan_moat" in report
    assert "buffett_valuation" in report
    assert "munger_inversion" in report
    assert "lilu_integrity" in report
    assert report["rigor_passed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_berkshire_committee.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `BerkshireCommittee` in `core/quant/berkshire_committee.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_berkshire_committee.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/quant/berkshire_committee.py tests/test_berkshire_committee.py
git commit -m "feat(quant): implement AI Berkshire qualitative research committee"
```

---

### Task 11: Bloomberg/Fincept Terminal UI Integration on `localhost:8900`

**Files:**
- Modify: `dashboard/server.py` (add quant pipeline telemetry endpoint `/api/quant/metrics` and `/api/berkshire/audit`)
- Modify: `dashboard/templates/index.html` (add Bloomberg multi-pane views: Order Depth Imbalance, Live 8-Stage Math Monitor, AI Berkshire Panel)
- Test: `tests/test_terminal_dashboard_api.py`

**Interfaces:**
- Consumes: Live streaming feeds from Binance/Coinbase/Kraken and `QuantPipeline`.
- Produces:
  - HTTP `GET /api/quant/metrics?symbol=BTCUSDT`: Returns all active 48-formula telemetry values.
  - HTTP `POST /api/berkshire/audit`: Triggers async qualitative research audit.
  - Multi-pane dark Bloomberg terminal dashboard on `http://localhost:8900`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_terminal_dashboard_api.py
import pytest
from fastapi.testclient import TestClient
from dashboard.server import app

def test_quant_metrics_endpoint():
    client = TestClient(app)
    response = client.get("/api/quant/metrics?symbol=BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert "stage1_data" in data
    assert "stage2_signal" in data
    assert "stage7_risk" in data

def test_berkshire_audit_endpoint():
    client = TestClient(app)
    response = client.post("/api/berkshire/audit", json={"symbol": "BTCUSDT"})
    assert response.status_code == 200
    data = response.json()
    assert "duan_moat" in data
    assert "buffett_valuation" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_terminal_dashboard_api.py -v`
Expected: FAIL

- [ ] **Step 3: Integrate endpoints and Bloomberg UI in `dashboard/server.py` and `dashboard/templates/index.html`**

Add the `/api/quant/metrics` and `/api/berkshire/audit` routes to FastAPI, attach the live `QuantPipeline` instances to the incoming market stream, and add the terminal view panels to `index.html`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_terminal_dashboard_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/server.py dashboard/templates/index.html tests/test_terminal_dashboard_api.py
git commit -m "feat(dashboard): add Bloomberg/Fincept multi-pane views and quant telemetry API"
```

---

### Task 12: End-to-End Regression & Verification Suite

**Files:**
- Modify: `tests/`
- Test: Full isolated test suite via `python -B scripts/run_isolated_tests.py`

**Interfaces:**
- Consumes: Entire workspace test suite.
- Produces: 100% test pass confirmation across existing 413 tests + new quant formula tests (target ~440+ tests passing, 0 failures).

- [ ] **Step 1: Run full isolated test suite**

Run: `python -B scripts/run_isolated_tests.py`
Expected: All tests pass with exit code 0.

- [ ] **Step 2: Verify active dashboard endpoints on `http://localhost:8900`**

Verify `/health`, `/ready`, `/api/quant/metrics`, and the visual terminal interface.

- [ ] **Step 3: Commit final integration**

```bash
git commit -am "chore(quant): complete 8-stage 48-formula quant engine and terminal integration"
```
