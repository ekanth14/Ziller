# Design Document: Institutional Quant Trading Engine & Bloomberg-Style Terminal (8 Stages, 48 Formulas)

**Date:** 2026-11-09  
**Status:** COMPLETE (Approved by User: Option 1)  
**Author:** Pair Programming Agent & User  
**Target File:** `docs/superpowers/specs/2026-11-09-quant-pipeline-and-terminal-design.md`

---

## 1. Intent & The "Why"
Automated trading systems fail primarily due to data leakage, unquantified market impact, overfitting, and unhedged risk exposure. This project implements an institutional-grade, mathematically complete quantitative trading pipeline consisting of **8 sequential stages and 48 deterministic formulas** inspired by the core training curricula of top financial institutions:
* **JPMorgan Chase Python Training (`jpmorganchase/python-training`)**: Vectorized numerical data manipulation, options pricing/straddles, clean time-series math, Altman Z''-score credit modeling.
* **Bloomberg Terminal SPA (`feremabraz/bloomberg-terminal`)**: Modular professional workstation UI (Movers, News, Volatility, Watchlists, AI summaries, keyboard shortcuts).
* **Fincept Terminal (`Fincept-Corporation/FinceptTerminal`)**: High-performance local caching, QuantLib analytics, and multi-asset intelligence.
* **AI Berkshire (`xbtlin/ai-berkshire`)**: Deterministic Python math via `Decimal` rigor checks, adversarial multi-agent research committees (Buffett, Munger, Duan Yongping, Li Lu lenses), and strict skill protocols.

This pipeline integrates into the existing **ZILLERS (`zien-crypto`)** platform while preserving all safety invariants, database integrity, and governance rules.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
1. **Mathematical Rigor (8 Stages, 48 Formulas)**:
   - **Stage 1 (Data Clean)**:
     - 1.1 Log return: $r = \ln(P_t / P_{t-1})$
     - 1.2 Annualized volatility: $\sigma_{\text{year}} = \sigma_{\text{bar}} \cdot \sqrt{365}$ (24/7 crypto)
     - 1.3 EWMA volatility: $\sigma_t^2 = \lambda \sigma_{t-1}^2 + (1-\lambda) r_{t-1}^2$ ($\lambda = 0.94$)
     - 1.4 ATR: $\text{TR} = \max(H-L, |H-C_p|, |L-C_p|)$, $\text{ATR} = \text{avg}_{14}(\text{TR})$
     - 1.5 Bad tick filter: $|r - \mu| / \sigma > 6 \to \text{flag / fallback}$
     - 1.6 Zero lookahead: $\text{position}_t = f(\text{data} \le t-1)$ (fill on open $t$)
   - **Stage 2 (Signal)**:
     - 2.1 Z-score: $z = (x - \mu_n) / \sigma_n$
     - 2.2 EMA: $\text{EMA}_t = \alpha P_t + (1-\alpha) \text{EMA}_{t-1}$, $\alpha = 2/(n+1)$
     - 2.3 Momentum 12-1: $\text{mom} = P(t-21) / P(t-252) - 1$
     - 2.4 RSI: $\text{RSI} = 100 - 100 / (1 + \text{avg gain} / \text{avg loss})$
     - 2.5 Order book imbalance: $I = (Q_{\text{bid}} - Q_{\text{ask}}) / (Q_{\text{bid}} + Q_{\text{ask}})$
     - 2.6 Funding carry: $\text{APR} = \text{funding per 8h} \times 3 \times 365$
   - **Stage 3 (Filter)**:
     - 3.1 $t$-statistic of returns: $t = \text{mean} / (\sigma / \sqrt{n})$
     - 3.2 ADF test: $\Delta y_t = \alpha + \gamma y_{t-1} + \varepsilon_t$
     - 3.3 Half-life: $\text{half-life} = -\ln 2 / \lambda$ (Ornstein-Uhlenbeck)
     - 3.4 Hurst exponent: $E[R/S] \propto n^H$
     - 3.5 Correlation: $\rho = \text{cov}(x, y) / (\sigma_x \sigma_y)$
     - 3.6 Regime switch: $\sigma_{20} / \sigma_{252} > 1.5 \to \text{high-vol regime}$
   - **Stage 4 (Edge)**:
     - 4.1 Expected value: $\text{EV} = p W - (1-p) L$
     - 4.2 Breakeven win rate: $p^* = 1 / (1 + W/L)$
     - 4.3 Expectancy in $R$: $E[R] = p R_{\text{win}} - (1-p) 1R$
     - 4.4 Profit factor: $\text{PF} = \text{gross wins} / \text{gross losses}$
     - 4.5 Bayesian win rate: $\hat{p} = (\alpha + \text{wins}) / (\alpha + \beta + n)$
     - 4.6 Net edge: $\text{net} = \text{gross} - 2(\text{fee} + \text{slippage})$
   - **Stage 5 (Size)**:
     - 5.1 Risk-based size: $\text{size} = \text{equity} \cdot \text{risk}\% / |\text{entry} - \text{stop}|$
     - 5.2 Kelly criterion: $f^* = p - (1-p)/b$
     - 5.3 Continuous Kelly: $f^* = \mu / \sigma^2$
     - 5.4 Volatility target: $w = \sigma_{\text{target}} / \sigma_{\text{realized}}$
     - 5.5 Risk parity: $w_i \propto 1 / \sigma_i$
     - 5.6 Liquidation price: $P_{\text{liq}} \approx P_{\text{entry}} \cdot (1 - 1/L + \text{mmr})$
   - **Stage 6 (Execute)**:
     - 6.1 Spread cost: $\text{spread} = (\text{ask} - \text{bid}) / \text{mid}$
     - 6.2 Microprice: $P_{\text{micro}} = (P_b Q_a + P_a Q_b) / (Q_a + Q_b)$
     - 6.3 Square-root impact: $\Delta P / P \approx \sigma \sqrt{Q / V}$
     - 6.4 VWAP: $\text{VWAP} = \sum p_i q_i / \sum q_i$
     - 6.5 Slippage: $\text{slip} = (\text{fill} - \text{expected}) / \text{expected}$
     - 6.6 Maker vs. taker: $\text{round trip} = 2 \times \text{fee}$
   - **Stage 7 (Risk)**:
     - 7.1 Max drawdown: $\text{DD} = (\text{peak} - \text{equity}) / \text{peak}$
     - 7.2 Recovery math: $\text{gain needed} = \text{DD} / (1 - \text{DD})$
     - 7.3 Value at Risk: $\text{VaR}_{95} = 1.645 \cdot \sigma \cdot V$
     - 7.4 Portfolio volatility: $\sigma_p = \sqrt{w^T \Sigma w}$
     - 7.5 Risk of ruin: $\text{ruin} = ((1-p)/p)^N$
     - 7.6 Hard kill switch: $\text{equity} < \text{peak} \cdot (1 - \text{DD}_{\max}) \to \text{stop}$
   - **Stage 8 (Validate)**:
     - 8.1 Sharpe ratio: $\text{SR} = \text{mean}(r - r_f) / \sigma \cdot \sqrt{365}$
     - 8.2 Sharpe $t$-stat: $t \approx \text{SR} \cdot \sqrt{\text{years}}$
     - 8.3 Multiple testing: $P(\ge 1 \text{ false}) = 1 - (1-\alpha)^N$
     - 8.4 Best of $N$ noise: $E[\max \text{SR}] \approx \sigma_{\text{SR}} \sqrt{2 \ln N}$
     - 8.5 Walk-forward: $\text{train } [t_0, t_1] \to \text{test } [t_1, t_2] \to \text{roll}$
     - 8.6 Monte Carlo: $\text{shuffle trades} \times 1000 \to 95\text{th pct DD}$

2. **Terminal Workstation Interface (`http://localhost:8900`)**:
   - Multi-pane Bloomberg/Fincept-inspired layout:
     - **Market & Depth**: Live charts, order book imbalance, microprice.
     - **Quant Monitor**: Real-time calculated indicators across the 8 stages.
     - **Risk & Governor**: Real-time VaR, drawdown monitor, and hard kill switch status.
     - **AI Berkshire Committee**: Multi-agent qualitative/thesis panel.

3. **100% Test Coverage**:
   - Unit tests for all 48 formulas with boundary conditions, edge cases (zero division, single element), and precision checks.

### Non-Goals
* Bypassing the 5-gate governor or placing unapproved real-money orders.
* Synchronously blocking the SSE streaming loop with heavy Monte Carlo simulations.

### Anti-Goals
* No lookahead bias (strict test for $t \le -1$).
* No unvalidated LLM numeric generation.

---

## 3. Builder Architectural Calls (Resolved)

1. **Pipeline Execution Model**:
   - **Streaming Engine (Stages 1–3, 5–7)**: Runs in low-latency real-time mode per bar/tick to compute real-time metrics (EWMA vol, ATR, Z-score, Microprice, VaR, Drawdown).
   - **Asynchronous Batch Validation (Stages 4 & 8)**: Stage 4 (trade-level edge metrics) and Stage 8 (walk-forward cross-validation, 1,000-iteration Monte Carlo trade shuffle) run asynchronously in a background worker or on-demand via the dashboard API, caching results in SQLite to keep the real-time SSE loop sub-millisecond.

2. **Operational Authority of Stages 6 & 7**:
   - Stages 6 and 7 are **pure deterministic analytical evaluators**. They compute microprice, market impact estimates, slippage, VaR, and drawdown metrics.
   - When Stage 7 detects a breach ($\text{equity} < \text{peak} \cdot (1 - \text{DD}_{\max})$), it raises an explicit advisory signal `kill_switch_triggered = True`. The existing, battle-tested **5-Gate Governor** retains exclusive authority to enforce process halts or cancel orders. No duplicate execution loops are created.

3. **Single-Asset vs. Portfolio Scope**:
   - **Single-Asset Pipeline**: Stages 1, 2, 6 evaluate each ticker (BTCUSDT, ETHUSDT, SOLUSDT) independently.
   - **Portfolio Coordinator**: A shared state aggregator synchronizes multiple asset series to compute the joint correlation matrix $\rho$ (Stage 3.5), risk parity allocations $w_i$ (Stage 5.5), and total portfolio volatility $\sigma_p = \sqrt{w^T \Sigma w}$ (Stage 7.4).

---

## 4. Human Decision (Confirmed: Option 1)
* **AI Berkshire Committee Integration (Interactive Terminal Tool)**:
  - The Berkshire multi-agent committee (Warren Buffett, Charlie Munger, Duan Yongping, Li Lu) is integrated as an on-demand, interactive qualitative research panel inside the Bloomberg/Fincept Terminal workstation (`http://localhost:8900`).
  - Users can select any monitored symbol (BTC, ETH, SOL) and trigger an asynchronous committee audit.
  - The committee delivers:
    - **Moat & Business Model Analysis (Duan Yongping lens)**: Competitive sustainability, network effects, fee generation.
    - **Intrinsic Value & Financial Soundness (Warren Buffett lens)**: Free cash flow proxy, tokenomics/staking sustainability, margin of safety.
    - **Lollapalooza & Inversion Audit (Charlie Munger lens)**: Incentive misalignments, multi-factor reflexive risks, systemic leverage risks.
    - **Management & Governance Risk Assessment (Li Lu lens)**: Developer team integrity, centralization vectors, regulatory and legal attack surface.
  - Because it runs on-demand via async endpoints, it introduces **zero latency** to the real-time sub-millisecond quantitative streaming engine.
