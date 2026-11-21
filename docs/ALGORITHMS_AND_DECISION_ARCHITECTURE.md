# ZILLERS — Algorithms, Strategies, Formulas, Quant Analytics & Decision Architecture

Reference for every trading rule, formula and decision layer in the project. Values quoted here are the defaults in code at the time of writing; the file named in each section is the source of truth.

> **Honesty note.** Nothing in this document claims a proven edge. The Strategy Lab and the desk scoreboard apply permutation tests with Bonferroni correction, and on current history most rules do **not** beat random timing. The project is a research and paper/testnet system. LIVE trading is locked behind a 5-gate governor and is never enabled by default.

---

## 1. System overview

Two cooperating decision systems share the same real Binance data:

| System | Purpose | Code |
|---|---|---|
| **Action Desk** | Human-facing, deterministic rule PM + AI veto overlay. Paper book, charts, scoreboard, Strategy Lab. | `cryptoscope/desk/` |
| **Autotrader fleet** | 10 asyncio bots on an event bus. Signal → proposal → debate → risk → execution on Binance Spot **Testnet** / paper. | `cryptoscope/orchestrator/` |
| **Quant library** | 8-stage, 48-formula pure-math core plus 10 "levels" of reference maths. | `core/quant/` |

Cross-cutting safety: persistent kill switch / halt latch (`GovernorState`), risk governor, protections, shadow OCaml risk gate, optional C++ kernels with Python fallback.

---

## 2. Decision architecture

### 2.1 Fleet pipeline (autotrading)

```
Scanner/Autopilot (pick top-5 coins)
        │
   DataBot  ── live candles via CandleStore (fresh, 1m price)
        │  MarketUpdate
   ┌────┼──────────────┬──────────────────┬───────────────────┐
AnalystBot       QuantBot        VolatilityBreakoutBot     StatArbBot
(EMA 9/21)   (vol regime + CVD)   (squeeze breakout)     (ETH/BTC pairs)
   └────┴──────────────┴──────────────────┴───────────────────┘
        │  Signal (direction, confidence)
   StrategyBot  ── confidence ≥ 0.65, spot-only, cooldown, 15-min dedupe,
        │           builds entry / stop / target (2:1 R:R)
        │  TradeIntent
   DebateBot    ── Ollama: Bull vs Bear vs Risk moderator, fail-closed
        │  DebateResult (conviction 1–10)
   RiskBot      ── 9 deterministic limits + protections + sizing
        │  RiskDecision (APPROVED / VETOED + approved USD)
   ExecutionBot ── paper / Binance Testnet, exchange-side protective stop
        │  Fill / PositionClosed
   JournalBot (SQLite) ── NotifierBot (Telegram)      SupervisorBot (watchdog)
```

**Fail-closed everywhere:** a debate timeout, invalid JSON, missing data or an engaged halt latch ends in REJECT / no trade, never a guess.

### 2.2 Desk pipeline (Action Desk)

```
Real candles (1m…1w)
   │
   ├─► 4 rule models vote +1/0/−1 ─► weighted score ─► PM: BUY / HOLD / SELL
   │
   ├─► AI overlay (closed bars only)
   │       SMC + Laya · Hedge-fund committee (+THX-02) · Strategy library · LLM panel (Ollama)
   │
   └─► VETO-ONLY merge:  AI can turn a PM BUY into HOLD.
                         AI can NEVER create a BUY or enlarge a position.
   │
   └─► Paper book: decision on bar t close → fill at bar t+1 open, fee per side (no lookahead)
```

### 2.3 Design principles

1. **No lookahead.** Decisions use bars up to and including `t`; fills happen at `t+1` open. The forming bar is shown but never used for decisions. Tests assert every Strategy Lab rule is causal.
2. **Veto-only AI.** Models can only make the system more conservative.
3. **Spot, long-only.** No shorting, no leverage (gross leverage cap 1.0).
4. **Real data only.** No synthetic candles; insufficient history returns `INSUFFICIENT_DATA`.
5. **Single halt authority.** One durable latch (`work/runtime/governor.db`); only the local admin clears it.
6. **Statistical honesty.** Permutation p-values, Bonferroni, out-of-sample splits, deflated Sharpe.

---

## 3. Action Desk engine — `cryptoscope/desk/engine.py`

### 3.1 Indicators

| Indicator | Formula |
|---|---|
| SMA(n) | mean of last n closes |
| EMA(n) | `EMAₜ = k·Pₜ + (1−k)·EMAₜ₋₁`, `k = 2/(n+1)` |
| RSI(14), Wilder | `RSI = 100 − 100/(1 + avg_gain/avg_loss)`, smoothed `(prev·13 + x)/14` |
| MACD | `EMA12 − EMA26`; signal `EMA9(MACD)`; histogram `MACD − signal` |
| ATR(14) | `TR = max(H−L, |H−Cₚ|, |L−Cₚ|)`, simple mean over 14 |
| Bollinger %b | `(C − (SMA20 − 2σ)) / (4σ)` |
| 20-bar return | `C / C₋₂₀ − 1` |
| Volume ratio | `volₜ / mean(vol of previous 20 bars)` |
| Drawdown | `C / running_peak − 1` |
| Annualised vol | `stdev₂₀(ln returns) · √bars_per_year` |
| Bars per year | `365·86400 / interval_seconds` (intervals 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w) |

### 3.2 Rule models (each votes +1 / 0 / −1)

| Model | Weight | Rule |
|---|---|---|
| Trend | 1.2 | +1 if SMA10 > SMA30, else −1 |
| Momentum | 1.0 | +1 if 20-bar return > +3%, −1 if < −3%, else 0 |
| Volume | 0.8 | spike > 1.40× avg20: +1 on a green candle, −1 on red; else 0 |
| Drawdown | 0.6 | −1 if dd < −25%; +1 if −25% ≤ dd ≤ −5% (dip-buy zone); else 0 |

### 3.3 Portfolio manager

```
score = Σ weightᵢ · voteᵢ          (max |score| = 3.6)
BUY  if score ≥ +1.2   (and flat)
SELL if score ≤ −1.2   (and long)
else HOLD
bull_pct = 50 + 50·score / 3.6
```

Execution: BUY fills at next open (`day_ret = close/open·(1−fee) − 1`), SELL at next open; trade net = `(1+gross)·(1−fee)² − 1`.

### 3.4 Scoreboard and significance

* Each model (and the PM) is scored against the return of the **next 5 bars**: hit-rate and mean edge = `mean(vote × fwd_return)` over bars where it voted.
* **Permutation test** (`significance`): keep the model's exact vote counts, shuffle the vote vector against real forward returns 1,000 times; `p = (#random edges ≥ real + 1) / (trials + 1)`.
* **Bonferroni:** 5 rules tested → each must clear `0.05 / 5 = 0.01` to be flagged significant.

### 3.5 Desk risk panel

ATR14, annualised vol, 1-bar historical VaR95 (5th percentile of returns), worst bar, max drawdown of the desk book vs buy-and-hold, annualised Sharpe `mean/std·√bars_per_year`.

---

## 4. AI overlay — `cryptoscope/desk/ai_layer.py`, `llm_panel.py`

| System | What it does | Output |
|---|---|---|
| **SMC + Laya** (`autotrader/decision.py`) | Tier 1 deterministic score (below). Tier 2 Laya classifier must agree; if slow (>200 ms), absent or failing → `STAND_ASIDE`. | LONG→BUY, SHORT→SELL, else HOLD |
| **Hedge-fund committee** (`core/agents/hedge_fund_committee.py`) | Personas vote; Risk Officer holds a hard veto. | BUY/SELL/HOLD + conviction |
| **THX-02** (`core/agents/thx02_decision_engine.py`) | Deterministic-ensemble regime/probability model inside the committee. | action, regime, conviction |
| **Strategy library** | Four autotrader strategies (§6.3) on the same closed bars. | SELL if any SELL, else BUY if any BUY |
| **LLM panel** | Every installed Ollama chat model answers once per model per bar (JSON only); majority of answered models decides. Paused while the kill switch is engaged or the fleet is running. | panel action |

**Merge rule:** if the rule PM says BUY and any system returns SELL or a risk veto → final = HOLD. Otherwise final = PM.

### 4.1 SMC + Laya Tier 1 composite score (−100…+100)

* Trend (EMA20/50/200 stack): ±25 (+5 bonus if also above/below EMA200).
* RSI zone: RSI ≥ 60 → `+min(25, (RSI−50)·1.5)`; RSI ≤ 40 → `−min(25, (50−RSI)·1.5)`.
* MACD: histogram and line both positive → +15, both negative → −15.
* Volume: ratio ≥ 1.5× SMA20 → ±15 depending on candle direction.
* SMC zone reaction: price inside an unmitigated bullish/bearish **order block** → ±20.
* Fair-value-gap / liquidity-sweep tags → ±10.
* Entry when `score ≥ 50`, trend up and near a bullish order block (mirror for shorts).

Structures: order blocks (displacement + unmitigated), fair value gaps (three-candle imbalance), liquidity sweeps (wick through prior swing then close back).

### 4.2 Hedge-fund committee

| Persona | Weight | Focus |
|---|---|---|
| Jim Simons | 0.35 | factor z-scores, momentum, volatility persistence |
| Cathie Wood | 0.25 | momentum acceleration, volume surges, breakouts |
| Buffett & Li Lu | 0.40 | moat, intrinsic value, margin of safety (BerkshireCommittee, `Decimal` maths) |
| Risk Officer | veto | VaR, drawdown, liquidation proximity |

```
norm_score = Σ(vote_score · weight · confidence) / Σ weight      vote_score ∈ {+1, 0, −1}
BUY if norm_score > +0.25,  SELL if < −0.25,  else HOLD
size = min(25%, max(2%, 0.5·Kelly)) · avg_confidence     (BUY only)
```

### 4.3 THX-02 deterministic ensemble

```
directional = 0.40·z + 0.30·(20·ROC5) + 0.20·(10·ROC20) + 0.10·tanh(CVD/5000)
logits → numerically stable softmax over {BUY, HOLD, SELL}
HIGH_VOL_CHOP logit = (vol − 0.03)·50 − |directional|
risk cleared if VaR < 5%, drawdown < 15%, vol < 6%, liquidation distance > 15%
regimes: TRENDING_BULLISH, TRENDING_BEARISH, HIGH_VOL_CHOP, LOW_VOL_CONSOLIDATION
```

Order-flow inputs are passed neutral on daily bars rather than invented.

---

## 5. Scanner, Autopilot & Markets directory

### 5.1 Market scanner — `cryptoscope/desk/scanner.py`

1. **Universe:** every TRADING Binance spot USDT pair (one 24h ticker call); testnet mode keeps only testnet-listed pairs.
2. **Filters:** drop stablecoins/fiat and leveraged tokens (UP/DOWN/BULL/BEAR); 24h quote volume ≥ $10M; |24h move| ≤ 25%.
3. **Shortlist:** 60 most liquid survivors get 90 daily candles.
4. **Factors:**
   * `r7`, `r30` returns; `vol30` = annualised vol of daily log returns
   * Risk-adjusted momentum `M = (0.4·r7 + 0.6·r30) / vol30`
   * Trend = `close > SMA20 and SMA10 > SMA30`; RSI14; ATR14%; drawdown from 90-day high
5. **Eligibility:** trend true, 45 ≤ RSI14 ≤ 78, drawdown ≥ −25%, `vol30 ≥ 10%`.
6. **Score:** `0.45·z(M) + 0.25·z(r7) + 0.20·z(ln quote volume) − 0.10·z(ATR%) + W_MOM·z(r21) + W_SIZE·z(−ln quote volume)`
   * **Liu–Tsyvinski–Wu factors** are shown as columns on the Scanner page. Each is a cross-sectional percentile rank (0 = weakest, 1 = strongest):
     * `mom_rank` ranks the 3-week return `r21` (CMOM factor).
     * `size_rank` ranks `−ln(24h quote volume)` (CSMB factor). Binance gives no market cap, so traded value stands in for size, and smaller coins rank higher.
   * `FACTOR_WEIGHTS` sets **W_MOM = W_SIZE = 0**, so the ranking is unchanged until the Strategy Lab validates these factors (§6.6). A test pins both weights at 0.
7. **Pick:** top 5 eligible. If none qualify (e.g. a broad bear market) the autopilot deliberately does not trade.

The Autopilot feeds the picks to the fleet; each entry must still pass the full pipeline in §2.1.

### 5.2 Markets directory — `desk/markets.py`

Lists every Binance spot symbol with 24h change, volume and filters; links to the desk and Strategy Lab.

---

## 6. Strategies

### 6.1 Fleet signal bots

| Bot | Rule | Confidence |
|---|---|---|
| **AnalystBot** (`trend_structure`, 15m) | EMA9/EMA21. Golden cross → BUY, death cross → SELL; continuation above/below EMA9 in trend | 0.75 cross, 0.65 continuation |
| **QuantBot** (`quant_alpha`) | Volatility regime (Parkinson / Garman-Klass / Yang-Zhang) + CVD divergence. Compression + breakout readiness > 60% + absorption → signal | 0.80 with compression, 0.70 CVD alone |
| **VolatilityBreakoutBot** | Squeeze (compression ratio < 0.70, lookback 24) then directional break with volume and CVD confirmation | up to 0.95 |
| **StatArbStrategyBot** | ETHUSDT vs BTCUSDT cointegrated pair, z-score bands | — |
| **StrategyBot** | Converts a Signal into a TradeIntent. See §6.2 | gate ≥ 0.65 |

### 6.2 Trade construction (StrategyBot)

```
risk_distance = max(1.5·ATR, 0.5% of price)
BUY: stop = entry − risk_distance,  target = entry + 2·risk_distance   (2:1 R:R)
horizon = 48 bars
```

* Spot-only: SELL signals are dropped (exits come from stop/target).
* Per-symbol cooldown 5 s; identical (direction, price) proposals suppressed for 15 minutes.

### 6.3 Autotrader strategy library — `cryptoscope/autotrader/strategies/`

| Strategy | Entry logic | Stop / target |
|---|---|---|
| **Volume Breakout** (放量突破) | Close breaks 20-bar swing high, volume ≥ 1.5× avg, RSI 50–75, EMA20 ≥ EMA50 | stop `min(low·0.998, swing_high·0.99)`; confidence `min(0.95, 0.65 + (vol_ratio − 1.5)·0.1)` |
| **Shrink Pullback** (缩量回踩) | Uptrend (EMA20 > EMA50), low within 1.5% of EMA20, pullback volume ≤ 0.75× avg, bullish rebound | stop below support wick ×0.995; target 2.2R; confidence `min(0.92, 0.70 + (0.75 − vol_ratio)·0.2)` |
| **Box Oscillation** (箱体震荡) | Range height 2.5–9% over 30 bars, price in bottom 25% of box, support rejection, RSI ≤ 50, R:R ≥ 1.2 | stop `box_low·0.992`, target upper box |
| **Volatility Compression Breakout** (波动率压缩突破) | Compression < 0.70, close beyond consolidation bounds, volume and CVD confirm | stop `max(1.5·ATR, 1.2·body)`, target 2.5R; confidence `min(0.95, 0.70 + (0.70−cr)·0.4 + (vol_factor−1)·0.05)` |
| **Stat-Arb Pairs** (统计套利) | OLS hedge ratio, ADF stationarity on spread, OU half-life ≤ 200, entry |z| ≥ 2.0 | exit |z| ≤ 0.25, stop |z| ≥ 3.5 |

### 6.4 Strategy Lab — 13 classic long-only strategies (`desk/strategy_lab.py`, page `/lab`; 11 research candidates in §6.6)

Each decides at close of bar `t`, fills at open of `t+1`, pays a per-side fee; no parameter is fitted.

| Family | Strategy | Rule |
|---|---|---|
| Trend | EMA cross | long while EMA12 > EMA26 |
| Trend | MACD + trend | MACD(12,26) > signal(9) and close > EMA100 |
| Trend | Supertrend | ATR(10)×3 trailing band; long above it |
| Trend | Ichimoku | close above cloud (max Senkou A/B, displaced 26) and Tenkan(9) > Kijun(26) |
| Trend | Heikin-Ashi | enter after 2 bullish HA candles; exit on first bearish |
| Trend | Parabolic SAR | (0.02 / 0.2); long while SAR below price |
| Trend | Golden cross | long while SMA50 > SMA200 |
| Breakout | Donchian / Turtle | enter close > highest high(20) of prior bars; exit close < lowest low(10) |
| Breakout | Keltner | enter close > EMA20 + 2·ATR(20); exit close < EMA20 |
| Breakout | Williams volatility breakout | enter close > open + 0.5·prev range; exit after 3 bars or close < SMA10 |
| Mean reversion | Bollinger | enter close < SMA20 − 2σ; exit close ≥ SMA20 |
| Mean reversion | RSI-2 (Connors) | enter RSI(2) < 10 and close > SMA100; exit RSI(2) > 70 or close > SMA5 |
| Momentum | Time-series momentum | 30-bar ROC > 0 and close > SMA50 |

**Metrics per strategy:** total return, CAGR, annualised volatility, Sharpe, Sortino, max drawdown, Calmar, trade count, win rate, profit factor, exposure, in-sample (first 70%) vs out-of-sample (last 30%) return, and a permutation p-value (same exposure placed at random, 1,000 shuffles) **Bonferroni-corrected across every candidate tested (24 with §6.6)**. Equity curves are compared with buy-and-hold.

### 6.5 Grid and DCA paper bots — `desk/paperbots.py`

* **GRID:** evenly spaced levels `L₀ < … < Lₙ` in `[lower, upper]`, equal quote per grid. Buy filled at `Lᵢ` → rest sell at `Lᵢ₊₁`; each round trip earns `qty·(Lᵢ₊₁ − Lᵢ)` minus fees.
* **DCA:** base order at market; safety order `k` at `entry·(1 − step·Σⱼ<ₖ step_scaleʲ)` with size `base·volume_scaleᵏ`; take profit at `avg_entry·(1 + tp)`; optional stop below last safety; new cycle after each take-profit.
* Paper only, 0.1% per fill, advance on real 1-minute candles, pause while the kill switch is engaged.

### 6.6 Research candidates, indicator catalog and the promotion gate

The research review found that **time-series momentum** and the **size and momentum factors** are the best-documented crypto effects, and that testing many indicators at once mostly produces false winners. So every new rule is only a *candidate*: it is shown in the Lab, but it is promoted only if it passes an out-of-sample gate after fees. Nothing here places orders.

**Indicator catalog** — `cryptoscope/desk/indicator_catalog.py`, library `pandas-ta-classic==0.9.0` (pinned in `requirements.txt`).

* Every indicator in every category except `math` (≈ 183 indicators → ≈ 365 feature columns on 1,000 bars), computed per coin and timeframe.
* **No lookahead:** the value at bar `t` uses bars `≤ t` only. `audit_lookahead()` recomputes the catalog on truncated histories and checks that no earlier value changes; `tests/test_indicator_catalog.py` runs it on the whole catalog.
* **Excluded** because they look ahead or are not per-bar series: `dpo` (centred), `tos_stdevall` (regression fitted on the whole series), the Ichimoku chikou span `ICS_*` (close shifted 26 bars back), `vp` (price bins), and `mavp`, `beta`, `correl`, `long_run`, `short_run`, `tsignals`, `xsignals` (need extra inputs).
* The Lab page lists counts per category, the exclusions and every feature's latest value.

**New Lab candidates** — `desk/strategy_lab.py`; all long-only, decided on bar `t`'s close and filled at `t+1`'s open.

| Family | Strategy | Rule |
|---|---|---|
| Momentum | Vol-scaled TS momentum | `z = ln(Cₜ / Cₜ₋₃₀) / (σ₃₀ · √30)` with σ₃₀ the sd of 1-bar log returns; enter `z > 1`, exit `z < 0` |
| Breakout | Keltner squeeze | squeeze = Bollinger(20, 2σ) inside Keltner(EMA20 ± 1.5·ATR20); enter on the first bar out of a squeeze with close > SMA20 and rising; exit close < EMA20 |
| Mean reversion | VWAP reversion | `VWAP20 = Σ(typical·vol) / Σvol`; enter `close − VWAP20 < −2·sd(close − VWAP20, 20)`; exit close ≥ VWAP20 |
| Trend | ADX + DI | long while ADX(14) > 25 and +DI > −DI |
| Trend | Aroon | long while Aroon-up(14) > 70 and up > down |
| Mean reversion | Stoch-RSI cross | enter %K crosses above %D below 20; exit %K > 80 |
| Mean reversion | CCI reversion | enter CCI(14) crosses back above −100; exit CCI > 0 |
| Mean reversion | MFI reversion | enter MFI(14) < 20; exit MFI > 50 |
| Trend | Hull MA | long while close > HMA(55) and HMA rising |
| Trend | KAMA | long while close > KAMA(10, 2, 30) and KAMA rising |
| Trend | Vortex | long while VI+(14) > VI−(14) |

Donchian/Turtle, Bollinger reversion, Keltner breakout, Supertrend, Ichimoku and 30-bar TS momentum were already among the 13 classics (§6.4); they go through the same gate. The Lab now tests 24 candidates, and the Bonferroni correction and the DSR use that count.

**Validation** — `core/quant/validation.py`

* **Triple-barrier labels.** Each entry (position 0 → 1) becomes the trade `StrategyBot` would place: `bracket("SCALP", ATR14 / close)` gives the target and stop (§6.2), and the 16 × 15 m = **4 h** time limit is converted to the Lab's interval (at least one bar). The first barrier touched decides the label. If one bar touches both, the stop is assumed first; a gap through a barrier fills at the open for stops and at the target for targets. Net return = `exit/entry · (1 − fee)² − 1`, fee = max(selected fee, **10 bp**) per side. One position at a time per coin.
* **CPCV.** The bars are split into N contiguous groups; every choice of k test groups gives one split (C(N, k) splits). A training observation is **purged** when its label window `[signal, exit]` overlaps a test group. An **embargo** of max(time-limit bars, 1% of bars) after each test group is also dropped.
* **PBO** (Bailey, Borwein, López de Prado & Zhu, CSCV). Build a `T × N` matrix of net trade returns, one column per candidate, each return booked on its signal bar. Take every half of 10 groups as in-sample: C(10, 5) = 252 purged and embargoed splits. In each split, pick the best in-sample Sharpe, find its out-of-sample relative rank ω, and compute `λ = ln(ω / (1 − ω))`. `PBO = P(λ ≤ 0)`. Known-answer tests: 20 pure-noise columns give PBO ≈ 0.5, and one planted edge among 19 noise columns gives PBO < 0.1.
* **Deflated Sharpe** — reused from `level10_research.compute_deflated_sharpe_ratio`. Inputs: per-trade Sharpe, trials = number of candidates, and the cross-candidate variance of Sharpe. `p = 1 − DSR`.

**Promotion gate** (per candidate, per symbol and interval)

| Test | Threshold |
|---|---|
| Out-of-sample trades: trades whose signal and exit fall inside one CPCV group | ≥ 100 |
| Deflated-Sharpe p | < 0.05 |
| PBO of the candidate set | < 0.3 |
| Expectancy (mean net trade return after fees) | > 0 |

* The Lab page shows a **GATE** column per candidate: OOS trades, expectancy, DSR p and PROMOTED, or the first failed test (hover for all of them). The warning line shows the set's PBO.
* Every `/api/lab` run rewrites the entries for that symbol and interval in `work/runtime/promoted_strategies.json`, so a strategy that stops passing is demoted. The write is atomic.
* `load_promoted_strategies()` reads the file and returns `[]` when it is missing or unreadable.
* **The bots do not read the file yet.** Wiring promoted strategies into `StrategyBot` is a separate, deliberate step.

**Limits, stated plainly**

* The Lab rules use fixed textbook parameters and never fit them to the data. So "out of sample" here guards against picking the luckiest of many candidates (DSR, PBO), not against parameter fitting.
* One Lab run sees at most 1,000 bars. On 15 m candles that is about 10 days, so most candidates cannot reach 100 OOS trades yet. On real BTCUSDT 15 m data (Nov 2026), no candidate passed.
* Bar data cannot show the order of moves inside a bar, so the labeller takes the conservative order. On 4 h or longer intervals, the 4 h time limit becomes a single bar.
* PBO is a property of the whole candidate set: adding more noise candidates moves it towards 0.5 for all of them.

---

## 7. Market-structure analytics — `desk/market_structure.py`

| Metric | Formula |
|---|---|
| Funding APR | `rate_8h · 3 · 365` |
| Basis (premium) | `(mark − index) / index` |
| OI change 24h | `OI_now / OI_24h_ago − 1` |
| Spread (bps) | `(ask − bid) / mid · 10,000` |
| Depth ±x% | `Σ price·qty` of bids ≥ `mid(1−x)` and asks ≤ `mid(1+x)` |
| Book imbalance | `(bid depth − ask depth) / (bid depth + ask depth)` within ±1% |
| Microprice | `(ask·bid_qty + bid·ask_qty) / (bid_qty + ask_qty)` |

Also long/short account ratio and taker buy/sell ratio (1h and 24h). Rule-of-thumb readings (e.g. funding ≥ +0.05%/8h = crowded longs; ≤ −0.03% = crowded shorts; OI up with price up = new longs) are context for a human, **not** trade signals. 1000× perpetuals are mapped (e.g. PEPEUSDT → 1000PEPEUSDT); spot-only coins show the order book alone.

---

## 8. Volatility & order-flow analytics — `cryptoscope/quant/`

| Estimator | Idea |
|---|---|
| Realized vol | stdev of log returns × √(bars/year) |
| Parkinson | uses high/low range: `σ² = (1/(4 ln 2)) · mean(ln(H/L)²)` |
| Garman-Klass | adds open/close terms for lower variance |
| Yang-Zhang | combines overnight, open-to-close and Rogers-Satchell components |

* **Compression ratio** = short-window GK vol / long-window GK vol. `< 0.65` → `COMPRESSION_SQUEEZE` (breakout readiness `70 + (0.65 − ratio)·100`, cap 98); `> 1.45` → `EXPANSION_VOLATILE`; else `NORMAL_FLOW`.
* **CVD** (cumulative volume delta) from taker-buy vs total volume; divergence between price and CVD flags bullish absorption / bearish exhaustion.
* **Stat-arb helpers** (`quant/stat_arb.py`): OLS hedge ratio, spread, ADF unit-root test, Ornstein-Uhlenbeck parameters, spread z-score.

---

## 9. Quant library — `core/quant/` (8 stages, 48 formulas)

| Stage | Formulas |
|---|---|
| **1 Data** | log returns `ln(Pₜ/Pₜ₋₁)`; annualised vol `σ√N`; RiskMetrics EWMA `σₜ² = λσₜ₋₁² + (1−λ)rₜ₋₁²` (λ=0.94); ATR; bad-tick filter `|r−μ|/σ > 6`; no-lookahead verifier |
| **2 Signal** | rolling z-score; EMA; 12-1 momentum `P(t−lag_s)/P(t−lag_l) − 1`; RSI; order-book imbalance `(Q_b−Q_a)/(Q_b+Q_a)`; funding carry APR `f·3·365` |
| **3 Filter** | return t-stat `mean/(σ/√n)` (< 2 ⇒ assume luck); ADF test; OU half-life `−ln2/λ`; Hurst exponent via R/S analysis; correlation matrix; high-vol regime `σ₂₀/σ₂₅₂ > 1.5` |
| **4 Edge** | EV `p·W − (1−p)·L`; breakeven win rate `1/(1+W/L)`; expectancy in R; profit factor (< 1.2 thin); Bayesian Beta-prior win rate; net edge `gross − 2(fee+slippage)` |
| **5 Size** | fixed-fractional `equity·risk% / |entry−stop|`; discrete Kelly `f = λ(p − (1−p)/b)`; continuous Kelly `λ·μ/σ²`; volatility target `min(maxLev, σ_target/σ_real)`; inverse-vol risk parity `wᵢ ∝ 1/σᵢ`; liquidation price |
| **6 Execute / TCA** | spread cost; microprice; square-root impact `ΔP/P ≈ c·σ·√(Q/V)`; VWAP; slippage `(fill−expected)/expected`; round-trip fee `2·fee` |
| **7 Risk** | max drawdown; recovery gain `DD/(1−DD)`; parametric VaR95 `1.645·σ·V`; portfolio vol `√(wᵀΣw)`; gambler's ruin `((1−p)/p)ᴺ`; hard kill switch `equity < peak·(1−DD_max)` |
| **8 Validate** | Sharpe `mean(r−r_f)/σ·√N`; Sharpe t-stat `SR·√years`; multiple-testing `1−(1−α)ᴺ`; best-of-N noise Sharpe `σ_SR·√(2 ln N)`; walk-forward windows; Monte-Carlo drawdown (shuffle trade order, percentile max DD) |

`core/quant/pipeline.py::QuantPipeline.on_bar` chains these per bar (stop = `close − 2·ATR`, size = 1% fixed-fractional risk, drawdown limit 15%) and a portfolio view (correlations, risk-parity weights, joint vol).

### 9.1 The ten reference levels — `core/quant/levels/`

| Level | Topics |
|---|---|
| 1 Probability | Bayes' rule, linearity/total expectation, variance, Gaussian / Student-t / Poisson / Exponential / Uniform densities and CDFs |
| 2 Statistics | standard error, Sharpe t-stat, OLS regression and hedge ratio, correlation/R², FWER, Bonferroni, Benjamini-Hochberg FDR |
| 3 Linear algebra | covariance, PSD check/repair, portfolio variance, PCA, condition number, safe inverse, Ledoit-Wolf shrinkage |
| 4 Optimization | Taylor expansion, gradient descent, Lagrange/KKT, minimum-variance and Markowitz `w* = Σ⁻¹μ/γ`, volatility drag `μ − σ²/2`, Jensen |
| 5 Time series | autocorrelation regime, ADF, cointegration hedge ratio, half-life, **GARCH(1,1)** `σₜ² = ω + αε² + βσ²` with fitting and forecast |
| 6 Stochastic | random walk, Brownian motion, **GBM** `S₀·exp((μ−½σ²)t + σW)`, Itô lemma, gambler's ruin, martingale test |
| 7 Derivatives | **Black-Scholes** call/put, put-call parity, Greeks (Δ Γ Θ ν ρ), implied-vol solver, gamma P&L |
| 8 Portfolio / risk | **CAPM**, **Fama-French 3-factor**, Sharpe, discrete/continuous Kelly, parametric VaR and Expected Shortfall, historical VaR/CVaR, max drawdown |
| 9 Microstructure | mid, spreads, multi-level imbalance, microprice, square-root impact, VWAP/TWAP, implementation shortfall, **Avellaneda-Stoikov** market making `r = s − qγσ²(T−t)` |
| 10 Research / ML | backtest-bias audit (lookahead, zero fees, survivorship, snooping), walk-forward validation and efficiency, **Deflated Sharpe Ratio**, classification metrics, **Gaussian regime HMM** (EM / Baum-Welch, Viterbi) |

### 9.2 Alpha158 factor engine — `core/quant/factors/alpha158.py`

Qlib-style features with strict zero lookahead: rolling SMA/EMA/std, rate-of-change (ROC5/ROC20…), MA-cross ratios, rolling volume volatility, cross-sectional and rolling z-scores. Feeds the committee and THX-02.

### 9.3 Native acceleration

Hot kernels (Hurst, Monte-Carlo drawdown, HMM, rolling factors) have C++ implementations in `native/src/zillers_native.cpp` behind a C ABI loaded via ctypes. Python versions remain the **source of truth and fallback**; on this Windows machine Application Control blocks the DLL, so the fallback runs.

---

## 10. Risk, protections and execution safety

### 10.1 RiskBot — `orchestrator/bots/risk_bot.py` (deterministic, no LLM)

| # | Check | Default |
|---|---|---|
| 1 | Debate verdict must be approved | conviction ≥ 6 |
| 2 | Daily loss limit (circuit breaker) | 3% of NAV |
| 3 | Portfolio max drawdown | 10% |
| 4 | Max open positions | 3 |
| 5 | Per-coin exposure | 15% NAV |
| 6 | Max single order | 5% NAV |
| 7 | Correlation cap vs open positions | 0.85 |
| 8 | Minimum 24h liquidity | $100k |
| 9 | Stop distance floor | ≥ 0.50% |
| — | Sizing | fixed-fractional 0.5% risk; half-Kelly only after ≥ 300 closed trades (gated) |

Breaker state persists across restarts (daily figures only within the same UTC day).

### 10.2 Protections — `execution/protections.py` (freqtrade-inspired)

| Guard | Default behaviour |
|---|---|
| Cooldown | lock a pair 30 min after any exit |
| StoplossGuard | ≥ 3 stop-losses in 6 h → lock all pairs 2 h |
| LowProfitPairs | last 3 trades on a pair sum ≤ −2% within 48 h → lock pair 12 h |
| MaxDrawdown | realised drawdown ≥ 8% in 48 h → lock all pairs 24 h |

Persisted; a restart never clears a lock.

### 10.3 RiskGovernor pre-trade checks — `execution/governor.py`

Evaluated fail-closed in order: emergency halt, stale feed (> 5 s), cross-feed divergence (> 1%), symbol allowlist, post-loss cooldown, trades-per-24h cap, total-drawdown halt, daily-loss halt, spot-only action check, 5% position cap, max open orders, on-chain token safety score (< 65 or DANGER).

### 10.4 Live-trading 5-gate governor

1. `LIVE_TRADING=true`
2. API key configured with **withdrawals disabled**
3. Forward paper gate: ≥ 28 days, ≥ 100 trades, positive net PnL after costs/tax model, drawdown ≤ 15%, Deflated Sharpe ≥ 0.80, forward execution only
4. Admin re-authentication within 5 minutes
5. Typed confirmation `ENABLE LIVE TRADING`

### 10.5 Kill switch and halt

* `HALT` cancels working orders and keeps protective stops; `HALT_FLATTEN` also closes positions. Both need admin re-auth to resume.
* The desk kill switch stops the autopilot, the fleet, the LLM panel (and unloads Ollama models).
* The execution layer reconciles with the exchange at start-up and periodically; mismatches halt.

### 10.6 Shadow risk gate (OCaml) — `ocaml/risk_gate`, `execution/shadow_gate.py`

A strongly-typed re-implementation of `check_pre_trade` run **beside** the Python governor purely to detect divergence. It has no authority over orders.

### 10.7 Execution model

Paper/software modes charge 0.1% per side and 0.05% slippage. Testnet mode places real testnet orders, accounts actual fills and commissions, and keeps an exchange-side protective stop; uncertain entries are reconciled and protection is repaired by `execution/lifecycle.py`.

---

## 11. Debate layer — `cryptoscope/agents/consensus.py`, `bots/debate_bot.py`

A single Ollama call returns JSON with `bull_thesis`, `bear_thesis`, `risk_verdict` (APPROVE/VETO), `conviction` (integer 1–10), `consensus_action`, `reason`.

```
approved  ⇔  conviction ∈ [6, 10]  AND  risk_verdict == APPROVE  AND  action == proposed direction
```

Anything else — timeout (default 35 s, desk fleet uses 90 s), HTTP error, invalid JSON, non-integer or out-of-range conviction — is a REJECT. The model is resolved from `OLLAMA_DEBATE_MODEL`, then `OLLAMA_MODEL`, then an installed Gemma model.

---

## 12. Governance, journals and observability

* **AI decision journal** (`desk/ai_journal.py`): records each system's call per bar and scores it against what happened next (accuracy scoreboard on the desk).
* **JournalBot:** SQLite audit trail of intents, risk decisions, fills and closes.
* **NotifierBot / Telegram:** one message per trade, close, halt and fleet start/stop, with IST timestamps and INR values.
* **SupervisorBot:** heartbeats and crash recovery with exponential backoff (max 5 restarts).
* **System monitor page:** CPU, memory, disk, latency/ping and data-delay metrics.
* **Display options:** IST/UTC and INR/USD toggles.

---

## 13. Known limitations

* Strategy Lab and desk results show no rule reliably beating random timing after multiple-testing correction on current history; rankings are descriptive.
* Order-flow inputs are neutral on daily bars (no taker data), so CVD-based signals are mostly inert there.
* The RiskBot correlation matrix is a static table for major pairs, not a live estimate.
* C++ and OCaml components are exercised in CI; locally the Python fallback runs.
* Telegram delivery and LIVE mode have not been exercised end-to-end by the assistant.

---

## 14. THX-02 + Laya meta-label filter and risk-only flow sizing (added 2026-11-20)

### 14.1 The two models

| | HAL-X-AI/THX-02 | convaiinnovations/laya (`typed-decisions`) |
|---|---|---|
| Kind | 4.5 B "decision model" (Qwen3.5-family backbone + readout) | ModernBERT-large encoder + decision head (421 M) |
| Answers | probabilities over supplied options (`noul` yes/no, `score`, `choice`) | same question types; never generates text |
| Trained for | ticket routing, classification, moderation — **not markets** | same — **not markets** |
| Runtime here | CPU, `think=False` (its thinker needs a GPU vLLM server) | CPU |
| License | Apache-2.0 | Apache-2.0 |

Both cards' benchmarks are self-reported. THX-02's card says a new domain needs a few hundred labelled examples before its confidence can be trusted, so here the models start in **shadow mode**.

**Not to be confused with:** `core/agents/thx02_decision_engine.py` (a deterministic *formula ensemble* historically named "THX-02") and the Tier-2 joblib classifier in `autotrader/decision.py`. The UI now labels these "formula ensemble" and "tier-2 classifier".

### 14.2 Architecture

```
StrategyBot ──TradeIntent(features)──► DebateBot ──┬─ LLM debate (qwen3:8b, Ollama)
                                                    └─ MetaLabeler.assess() ──HTTP 127.0.0.1:8950 + token──► sidecar
                                                                                          (WSL on Windows: Application Control
                                                                                           blocks PyTorch DLLs on the host)
DebateResult.meta = {thx02_p, laya_p, mean_p, quality, enforced, vetoed}
      │
      ├─► JournalBot  → meta_labels table (always)
      └─► RiskBot     → META_LABEL_SKIP veto only if ZILLERS_META_ENFORCE=1 and mean_p < ZILLERS_META_MIN_P (0.5)
```

* Questions: `take` — "will the target be hit before the stop within the time limit?" (noul → P(yes)); `quality` — 5-level score.
* State text: coin, bracket, fee-adjusted win/loss and break-even win rate, tier, RSI, ATR%, 4h/24h returns, spread, depth, order-book imbalance, bar-VPIN and its percentile, volatility regime, strategy confidence.
* **Fail open**: no sidecar, timeout or model error → no opinion → never vetoes. The models can never add a trade or raise a size.
* **Proof before enforcement**: the P&L page compares closed trades the models said *take* vs *skip* (per model and combined). It recommends enforcing only after ≥ 100 judged trades and only if skipped trades had negative and lower expectancy.
* Setup: `scripts/download_decision_models.py` (weights pinned to a commit in `REVISIONS.json`), `cryptoscope/models_sidecar/server.py`, `cryptoscope/agents/decision_models.py`. START ALL starts the sidecar and test-asks each model. The kill switch stops it.

### 14.3 Risk-only flow and regime sizing — `cryptoscope/quant/flow_risk.py`

| Input | Formula | Use |
|---|---|---|
| Bar VPIN | `Σ|taker_buy − taker_sell| / Σ volume` over 20 bars (15m) | toxic if in the top 10% of its own history **and** ≥ 1.5× its median → size × 0.5 |
| Volatility regime | `σ(last 20 log returns) / σ(all ~60)` | ≥ 1.5 HIGH_VOL → × 0.5; ≥ 2.5 EXTREME_VOL → × 0.25 |
| Order-book imbalance | `(bid$ − ask$)/(bid$ + ask$)` within ±0.5% of mid (REST depth at decision time) | meta-label feature only |

* The smallest factor wins, and it is applied **after** every notional cap, clamped to [0, 1].
* **Approximations:**
  * Bar VPIN uses kline taker volume, not trade-by-trade volume buckets.
  * The regime is a volatility ratio rather than an HMM, because ~60 bars are too few to fit one.
  * True OFI (Cont et al.) needs a live depth stream, so a single depth snapshot is used instead.

### 14.4 Research notes behind §14

* **Time-series momentum** is the best-documented crypto effect. Size, momentum and market factors price the cross-section of coins (Liu & Tsyvinski; Liu, Tsyvinski & Wu).
* **Order-flow imbalance** predicts only very short horizons. **VPIN** helps more with volatility and jumps than with direction.
* **Funding/basis carry** has compressed to roughly 3–5% a year and has failed out-of-sample tests. It also needs perpetual shorts, so it stays analytics-only on this spot terminal.
* **Triple-barrier labels, meta-labeling, CPCV, PBO and the Deflated Sharpe Ratio** (López de Prado; Bailey et al.) guard against false winners. They decide what is promoted (see the Strategy Lab section).

### 14.5 How every bot and algorithm connects (2026-11-21)

```
Scanner (tiers, spread/depth filter, risk-off) ─► Autopilot ─► FleetManager ─► fleet child process
   │ logs tier per coin → work/runtime/scanner_tiers.jsonl
   ▼
DataBot (250 closed 15m bars + taker volume, live price)
   ├─► AnalystBot (EMA 9/21 trend)          ─┐
   ├─► QuantBot (vol regime, CVD order flow) ─┼─► Signal ─► StrategyBot
   └─► LabSignalBot (Lab strategies that      ─┘      bracket from real ATR(14); features: RSI, 4h/24h return,
        PASSED the gate for this coin + 15m)            EMA trend, VPIN, vol regime, scanner tier
                                                        │ TradeIntent
                                                        ▼
                    DebateBot ── qwen3:8b debate  +  THX-02 / Laya meta-label (sidecar; + spread, depth,
                        │                             book imbalance from one depth snapshot)
                        ▼ DebateResult(meta)
                    RiskBot ── gates (debate verdict, META_LABEL_SKIP if enforced, daily cap, protections,
                        │      exposure) → size × VPIN/regime multiplier (≤ 1)
                        ▼
                    ExecutionBot (PAPER / TESTNET) ─► JournalBot (incl. meta_labels) ─► P&L page
                                                  └► NotifierBot (Telegram)
Strategy Lab (28 candidates: 13 classics, 11 research/catalog rules, 4 desk-library rules)
   └─ CPCV + PBO + DSR gate ─► promoted_strategies.json ─► LabSignalBot   (today: 0 promoted)
```

* Desk-only systems (rule PM, SMC + tier-2 classifier, hedge-fund committee + formula ensemble, HMM) still drive the Action Desk view only.
* The desk's strategy library now reaches the fleet the same way every other strategy does: through the Lab gate.
* START ALL reports which promoted strategies are live in the fleet (check `promoted`).

---

## 15. Deep-research additions (2026-11-21) — `docs/research/Crypto algo strategies and formulas.md`

The research found that the best-supported additions are **evaluation statistics, exits and overlays**, not new alpha signals. Most crypto evidence ends by 2021 or covers bull windows, so the Lab gate on our own data decides.

### 15.1 Metrics — `core/quant/metrics_extra.py` (shown in the Lab: PSR, SQN columns)

| Metric | Formula |
|---|---|
| Probabilistic Sharpe (PSR) | `Φ((SR − SR*)·√(n−1) / √(1 − γ₃SR + (γ₄−1)/4·SR²))`, SR per period, γ₄ raw kurtosis |
| Min track record length | `1 + (1 − γ₃SR + (γ₄−1)/4·SR²)·(z_α/(SR − SR*))²` |
| Sortino | downside deviation over **all** n periods |
| Ulcer index / UPI | `√mean(DD%²)`; UPI = annual return % / UI |
| Omega(0) | `Σmax(r,0) / Σmax(−r,0)` |
| Tail ratio | `|P95| / |P5|` |
| Gain-to-pain | `Σr / |Σr⁻|` |
| SQN (Van Tharp) | `√min(N,100)·mean(R)/sd(R)` |
| K-ratio (Kestner 2003) | `slope(log equity) / (SE(slope)·√n)` |
| MAR | CAGR / |max DD| over the full history |
| Fractional differencing | `w₀=1, w_k = −w_{k−1}(d−k+1)/k`, truncated at \|w\| < 1e-4 (FFD) |

### 15.2 New gated Lab candidates (37 total)

| Candidate | Rule |
|---|---|
| Donchian 20 + Chandelier exit | Entry: close above the 20-bar high. Exit only below `HH since entry − 3·ATR(22)`, a stop that only ratchets up |
| TS momentum + Chandelier exit | Same exit applied to the time-series-momentum entry |
| EMA cross + ATR trailing stop | EMA 12/26 cross. Exit below `highest close − 2.5·ATR(14)` |
| NR7 breakout (Crabel) | Narrowest range of 7 bars. Long on a close above its high within 3 bars. Exit after 5 bars or below its low |
| Inside-bar breakout | Long on a close above the mother bar's high. Exit below its low or after 5 bars |
| Connors RSI < 10 | `CRSI = mean(RSI₃(close), RSI₂(streak), PercentRank₁₀₀(1-bar return))`, above SMA200. Exit when CRSI > 70 |
| Z-score reversion 20 | Long when z < −2 above SMA100. Exit at z ≥ 0 |
| Turn of month | Daily bars only. Hold from the last day of the month to day 3 |
| UTC-day opening-range breakout | Intraday bars only. Range = first hour of the UTC day. Long above it, flat at day end |

Why the exits are wide: Kaminski & Lo (2014) show that stop-losses lower expected return under a random walk and help only when returns trend.

### 15.3 Cross-sectional momentum rotation — `cryptoscope/desk/rotation.py` (Lab panel, research only)

**Rules:**
* Weekly rebalance.
* Score = mean percentile rank of 7/14/21/28-day returns.
* Hold the top k coins with a positive return, equal weight.
* Keep a holding while its rank is within the top 2k.
* BTC gate: hold cash while BTC is below its 50-day SMA.
* Fees are charged on turnover.
* The universe is chosen **point-in-time** by trailing 30-day dollar volume.

**First live run (1,000 daily bars):**

| Universe selection | Out-of-sample return |
|---|---|
| Today's top 25 coins (biased) | +107% |
| Point-in-time, k = 3 | **−7%** (PSR 0.56) |
| Point-in-time, k = 5 | +28% (PSR 0.79) |

Neither point-in-time run has 100 out-of-sample entries, so neither passes.

**Residual bias:** coins delisted before today are missing from the candidate pool.

### 15.4 Deferred (with reasons)

| Item | Reason |
|---|---|
| Hedged pairs, copula and Johansen baskets | Every result that survived costs needed a short leg (futures) |
| Funding, basis and open-interest filters | Need a futures data feed |
| Hourly seasonality as a standalone strategy | Gross edge per trade is ≈ 0.045%, well below the 0.2% round trip |
| Almgren-Chriss, VWAP and POV scheduling | At retail size, fees and spread outweigh market impact |
| Meta-labeling with gradient boosting, and a jump-model regime filter | Next candidates; THX-02/Laya already provide a veto-only meta-label |

---

## 16. Dependencies, market filters, jump model, meta-labeling (2026-11-21)

### 16.1 Environments (Windows Application Control blocks some native DLLs on this machine)

| Environment | Contents | Why |
|---|---|---|
| `.venv` (Windows) | `requirements.txt` + `requirements-ci.txt` (numpy 2.5.4, pandas 3.1.1, LightGBM, onnxruntime, IPython) | Main runtime and tests. `pip check` is clean. |
| `work/environments/backtesting` | `quantjourney-bt` (pinned commit), numba 0.68, pandas 2.3 | Pins conflict with the main runtime. Its 13 engine tests pass there: `PYTHONPATH=. work/environments/backtesting/Scripts/python.exe -m pytest cryptoscope/tests/test_feature_integration.py cryptoscope/tests/test_repository_extensions.py` |
| WSL `~/.zillers-models-venv` | PyTorch CPU, `thx02`, `laya` | PyTorch DLLs are blocked on Windows |
| WSL `~/.zillers-dev-venv` | mypy 2.4.1 | mypy's compiled modules are blocked on Windows. CI runs `mypy -p cryptoscope.auth -p cryptoscope.fx -p cryptoscope.market_data` (now blocking; clean) |

**Not installed:**
* `quantstats` 0.0.64 requires numpy < 2, which conflicts with the runtime.
* scikit-learn's tree models are blocked by Application Control, so LightGBM is used instead.

### 16.2 Market filters — `cryptoscope/quant/market_filters.py` (RiskBot, veto-only, fail open)

* **Funding filter (on):** vetoes a new long when the coin's Binance USD-M perpetual funding is above **+0.05% per 8 h**.
  * Data comes from the public `fapi/v1/premiumIndex` endpoint (no key needed).
  * Coins without a perpetual are not affected.
  * Off switch: `ZILLERS_FUNDING_FILTER=0`. Threshold: `ZILLERS_FUNDING_MAX`.
* **BTC trend gate (opt-in, `ZILLERS_BTC_GATE=1`):** blocks new longs while BTC's daily close is below its 50-day SMA.
  * It is off by default because it stops **all** new entries during a BTC downtrend.
  * On 2026-11-21 BTC closed at 58,952 against an SMA of 77,718.

### 16.3 Statistical jump model — `core/quant/jump_model.py` (Lab candidate "Jump-model bull regime")

The model has two states and is fitted on past bars only.
* **Objective:** `min Σ‖x_t − θ_{s_t}‖² + λ·#switches`, with λ = 20.
* **Features:** standardised 10-bar mean return and volatility.
* **Refits:** every 50 bars.
* **Between refits:** a trailing 60-bar window is Viterbi-decoded with the fitted centroids, so evidence can build up over several bars before a switch.
* **Test result:** 82% accuracy on planted regimes with 9 switches.

### 16.4 Meta-labeling — `core/quant/meta_ml.py` (Lab panel "META-LABELING")

**Pipeline:**
1. Primary entries are taken from a Lab strategy.
2. Each entry is labelled with the bot's own triple-barrier bracket, including fees.
3. Nine features are computed at the signal bar only.
4. A LightGBM model is trained walk-forward with purging (only trades that exited before the test block) and a 2-signal embargo. A numpy logistic regression is used if LightGBM is unavailable.
5. The output compares out-of-sample expectancy of all trades, trades the model takes, and trades it skips.

**First live runs (XRP 15m):** out-of-sample AUC was 0.34–0.53, with no improvement in expectancy, so the filter is not used.
