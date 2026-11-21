# Build Spec: ZILLERS India — an Indian stock-market trading terminal

> **For the AI (or developer) building this.** This file is a complete, self-contained brief. It describes an existing crypto terminal (ZILLERS) and how to rebuild the same architecture, decision pipeline, safety model and UI for the **Indian stock market (NSE/BSE)**.
>
> **How to read it:**
> - Sections are ordered by build priority.
> - Every **MUST** is a hard requirement.
> - Every **VERIFY** marks a market rule, fee or regulation that changes over time. Check it against the official source listed before coding it, and keep all such values in one config file, never hard-coded in logic.
>
> Written 2026-11-21 from the ZILLERS crypto codebase (Python 3.12, stdlib HTTP dashboard, asyncio bot fleet).

---

## 0. One-paragraph summary

Build a **local, single-user trading terminal for Indian equities**, with these parts:
- **Scanner:** picks liquid, trending NSE stocks.
- **Bot fleet:** an event-driven chain of small bots that turns market data into signals, then trade proposals. Each proposal goes through an **LLM debate**, a **meta-label check** (THX-02 / Laya decision models), **deterministic risk gates**, then **paper execution** (live only behind a 5-gate unlock).
- **Strategy Lab:** backtests ~30 strategies and promotes only those that pass **overfitting tests** (CPCV, PBO, Deflated Sharpe) after Indian costs and taxes.
- **P&L page:** shows whether anything actually makes money.
- **Look:** a dark "chrome-on-black" theme with seven pages.

Everything runs on the user's machine. Paper trading is the default, and live trading is off unless the user deliberately unlocks it.

---

## 1. Non-negotiable safety rules (copy these exactly)

1. **PAPER is the default mode.** Modes: `OBSERVE` (no orders), `PAPER` (simulated fills on live prices), `LIVE`. India has no general broker testnet, so there is no `TESTNET` mode unless the chosen broker offers a sandbox (VERIFY per broker).
2. **LIVE requires a 5-gate unlock.** Every gate must be true at the moment of each order:
   1. config flag `LIVE_TRADING=true`;
   2. broker session valid;
   3. kill switch released;
   4. daily-loss and drawdown breakers not tripped;
   5. explicit operator confirmation in the UI, re-authenticated with the admin password.
   Never weaken or bypass a gate in code.
3. **Kill switch (master halt).** One button halts everything: stop all bots, cancel open orders, optionally square off. The halt is a **latch**: only the admin can clear it, from the local machine, with the password. No code path may clear it automatically.
4. **Secrets never enter the dashboard process.**
   - Broker API key, secret, access token and TOTP seed live in `.env` (git-ignored).
   - Only the execution child process reads them.
   - Logs, the UI and Telegram never print them.
   - Run a secret scanner in CI.
5. **AI handles no credentials.** Broker login (password, TOTP/2FA, daily access-token generation) is done by the human. The app may open the broker's login URL and receive the redirect, but must never store a password or TOTP seed it was not explicitly configured with.
6. **Models can only veto.**
   - LLMs and decision models never create a trade and never increase size.
   - Any model error, timeout or missing model means "no opinion". It never blocks trading and never approves a trade on its own.
   - The LLM debate fails **closed**: if it is unavailable, the proposal is rejected.
7. **Risk sizing can only shrink.** Every volatility, toxicity or regime multiplier is clamped to [0, 1] and applied **after** all notional caps.
8. **No lookahead anywhere.** Every feature at bar *t* uses bars ≤ *t*. Write a truncation test for every indicator and strategy: removing future bars must not change past values.
9. **Honesty in the UI.**
   - Label every metric with its source.
   - Never show a backtest as a promise.
   - Show net-of-costs numbers by default.
   - If nothing beats chance, the Lab must say so.
10. **Regulatory.** This is for the user's **own account only**.
    - Publishing signals or advice to others needs SEBI RA/IA registration.
    - Automated orders through a broker API must follow SEBI's retail algo framework (see §4.6).
    - Not investment or tax advice.

---

## 2. What to replicate (architecture of the existing crypto terminal)

### 2.1 Process layout

```
┌──────────────────────────── Dashboard process (stdlib http.server, port 8900) ────────────────────────────┐
│ Static pages (HTML + vanilla JS + one CSS file) · REST JSON API · session auth (admin role) · rate limits │
│ Scanner + Autopilot · Strategy Lab · Paper bots · START ALL self-test runner · P&L aggregator             │
│ NEVER holds broker secrets. Talks to children only via files/HTTP on 127.0.0.1.                           │
└───────────────┬─────────────────────────────────────┬───────────────────────────────────────┬────────────┘
                │ spawns                               │ spawns                                │ HTTP
                ▼                                      ▼                                       ▼
   Fleet child process (asyncio)          Decision-model sidecar (separate venv,        Ollama (local LLM server,
   python -m app.orchestrator             torch; THX-02 + Laya) 127.0.0.1:8950,          127.0.0.1:11434)
   --mode PAPER --symbols ...             bearer token, veto-only meta-labels           debate model e.g. qwen3:8b
   (only this process reads broker keys)
```

### 2.2 The bot fleet (event bus, one asyncio process)

All bots subscribe to typed events on an in-process `EventBus`. A `SupervisorBot` registers every bot, starts it, and watches heartbeats and health.

```
DataBot ── MarketUpdate(symbol, price, bid, ask, candles[], source) ──┬─► AnalystBot   ─┐
                                                                      ├─► QuantBot     ─┼─► Signal ─► StrategyBot
                                                                      ├─► LabSignalBot ─┘
                                                                      └─► StrategyBot (keeps latest candles)
StrategyBot ── TradeIntent(entry, stop, target, horizon, features{}) ─► DebateBot
DebateBot   ── (LLM debate ∥ THX-02/Laya meta-label) ── DebateResult(verdict, conviction, meta{}) ─► RiskBot
RiskBot     ── RiskDecision(APPROVED/VETOED, qty, size, veto_reasons[]) ─► ExecutionBot
ExecutionBot── OrderRequest / Fill / PositionClosed ─► JournalBot (SQLite) ─► P&L page
NotifierBot ── SystemAlert → Telegram (rate-limited, optional)
```

**Event schemas.** Use dataclasses; every event has `event_id` and `timestamp`.

| Event | Key fields |
|---|---|
| `MarketUpdate` | symbol, price, bid, ask, volume, spread_pct, candles (list of OHLCV dicts), source |
| `Signal` | signal_id, strategy_id, symbol, timeframe, direction (BUY/SELL/HOLD), confidence 0–1, indicators{}, reasons[] |
| `TradeIntent` | intent_id, strategy_id, symbol, direction, entry_price, stop_loss, take_profit, horizon_bars, reasons[], metadata{features{}} |
| `RiskPreApproved` | intent_id, symbol, prices, strategy_id, intent |
| `DebateResult` | intent_id, verdict (APPROVE/REJECT), conviction_score, bull_thesis, bear_thesis, risk_summary, latency_ms, fallback_used, meta{thx02_p, laya_p, mean_p, quality, enforced, vetoed, errors} |
| `RiskDecision` | intent_id, decision, approved_quantity, position_size_usd → rename **position_size_inr**, stop_distance_pct, veto_reasons[] |
| `OrderRequest` | client_order_id, symbol, side, qty, order_type, product (CNC/MIS), price, trigger_price |
| `Fill` | order_id, symbol, side, quantity, executed_price, charges_inr{brokerage, stt, exchange, sebi, stamp, gst, dp}, mode |
| `PositionClosed` | symbol, side, entry, exit, qty, pnl_inr (net of all charges), pnl_pct, duration_s, exit_reason |
| `SystemAlert` | severity, source, message |

### 2.3 Dashboard pages (same seven pages)

| Route | Page | Crypto version shows | India version must show |
|---|---|---|---|
| `/` | **Desk** | chart, rule-model votes, AI overlay, agent mesh, equity | same, for one NSE stock or index; plus market-status chip (Pre-open / Open / Closed / Holiday) |
| `/markets` | **Markets** | all Binance spot pairs | all NSE EQ stocks: LTP, % change, turnover (₹ Cr), 52-week high/low, circuit band, sector, F&O flag, ASM/GSM flag |
| `/scanner` | **Scanner** | top performers + autopilot | top NSE picks with tier (TREND / SHORT_TERM / POTENTIAL), exclusion reasons, autopilot |
| `/lab` | **Strategy Lab** | backtests, formulas, indicator catalog, promotion gate | same, with Indian cost model and tax-aware net returns |
| `/bots` | **Bots** | grid/DCA paper bots | SIP/DCA paper bots, grid only on liquid stocks |
| `/system` | **System** | START ALL, device, network, data delay, AI systems, protections, Telegram, fleet | same, plus broker session status and token expiry, exchange status, holiday calendar |
| `/pnl` | **P&L** | period P&L, equity curve, stats, positions, by exit reason, by tier, meta-label filter, funnel, vetoes, fills | same, in ₹, with a **charges and taxes breakdown** column |

---

## 3. UI and theme spec (replicate the look exactly)

### 3.1 Design tokens (CSS custom properties on `:root`)

```css
:root{
  --bg:#050506; --bg2:#0d0e11; --panel:rgba(20,21,25,.82); --panel2:rgba(34,36,42,.7);
  --line:rgba(220,225,235,.12); --txt:#e6e8ee; --muted:#8b919e;
  --green:#2ee6a6; --red:#ff5d7d; --blue:#6aa8ff; --amber:#ffc56b; --violet:#b18cff; --pink:#ff7ac0; --cyan:#4fe3ff;
  --accent:#d9dde6; --accent2:#2ee6a6;
  --chrome:linear-gradient(180deg,#ffffff 0%,#c9ced8 38%,#7d838f 52%,#e4e7ee 70%,#9aa0ab 100%);
  --m-trend:#ffc56b; --m-momentum:#b18cff; --m-volume:#6aa8ff; --m-drawdown:#ff7ac0;
  --radius:14px; --radius-sm:8px; --shadow:0 8px 30px rgba(0,0,0,.6);
  --font:"Inter","Segoe UI",system-ui,-apple-system,sans-serif;
  --mono:"JetBrains Mono","Cascadia Mono",ui-monospace,Consolas,monospace;
}
```

* **Brand.**
  * Header: logo + wordmark (chrome gradient text via `background:var(--chrome); -webkit-background-clip:text; color:transparent`) + page name.
  * Faint brand watermark in `body::before`.
  * Footer: brand line + "Paper money only unless LIVE is unlocked".
* **Colour meaning.** Green means up or OK, red means down or fail, amber means warning or trend. Never use colour alone; pair it with a sign or label (`+1.2%`, `FAIL`).
* **Numbers** use the mono font, right-aligned (`.num`).
* **Layout.**
  * A sticky **strip** under the header: mode chip, kill-switch state, market status, IST clock, ₹/units toggles.
  * Horizontally scrollable **nav** of the seven pages.
  * Pages are built from **panels** (`.panel` with `.ph` header row).
  * Tables sit inside `.tbl-wrap{overflow-x:auto}`.
* **Responsive (MUST).**
  * No horizontal page scroll at 375 px.
  * At ≤ 900 px the strip becomes static.
  * At ≤ 600 px panels stack one per row and font sizes step down.
  * Chips get their own full-width wrapping row (`order:10; flex:1 1 100%; flex-wrap:wrap`); chip text never wraps mid-word (`white-space:nowrap`).
* **India-specific formatting (MUST).**
  * Currency `₹`, using Indian digit grouping via `Intl.NumberFormat('en-IN')`: 1,23,45,678.
  * Large values in **lakh / crore** (`₹12.4 L`, `₹3.2 Cr`).
  * Time always **IST** (UTC+05:30, no DST); no UTC toggle needed.
  * Dates as `21 Nov 2026`.
* **States.** Every panel has loading, empty ("No closed trades yet.") and error states. Poll APIs every 15 s, and every 2 s while START ALL runs.

### 3.2 Page details

* **Desk:**
  * Candlestick chart (any lightweight chart lib pinned by version, or hand-drawn canvas) with EMA20/50/200, volume and VWAP.
  * "Model votes" panel: each rule model's +1/0/−1 and the PM's final action.
  * "AI overlay": committee, formula ensemble, LLM explainer status.
  * "Agent mesh": live health of each fleet bot.
  * Market-status chip and countdown to open or close.
* **Markets:** sortable, filterable table; filters for sector, Nifty index membership, F&O-only, hide ASM/GSM; search by symbol or name.
* **Scanner:**
  * Top-N cards with tier tag, score and "why".
  * Full universe table with exclusion reason per row.
  * Autopilot panel (on/off, mode, last action, next rescan).
  * "Method" panel explaining the formula in plain words.
  * Risk-off banner when the market regime is risk-off.
* **Lab:**
  * Controls: symbol, interval (5m / 15m / 1h / 1d / 1w), cost profile (delivery / intraday), RUN.
  * Results table: return, CAGR, Sharpe, Sortino, max DD, Calmar, trades, win %, profit factor, exposure, in-sample, OOS, p, OOS trades, expectancy, DSR p, **GATE** (✓ / ✗ with reason).
  * Banner: "No strategy beats random timing after correcting for N tests" when true.
  * Formulas panel; indicator-catalog panel.
* **Bots:** create a paper bot (DCA/SIP on an index ETF such as NIFTYBEES, or grid on a liquid large-cap); table of bots with invested, equity, P&L, vs-hold, fills.
* **System:**
  * **START ALL** panel: mode select (OBSERVE / PAPER / LIVE-locked), button, verdict ("All N models and systems are on board" or "NOT on board: …"), grouped checklist with status, latency and detail.
  * Panels for device, network latency, market-data delay, AI systems, protections, Telegram, fleet.
  * Broker session panel: logged in or out, token expiry time, **"Log in to broker"** button that opens the broker's own login page; the human completes login and 2FA.
* **P&L:**
  * KPI tiles: net P&L ₹, realised, unrealised, charges paid, taxes estimate, win rate vs **break-even win rate**, max drawdown.
  * Period table (today / 7d / 30d / FY-to-date / all).
  * Equity curve; daily P&L bars.
  * Tables: open positions (mark, uP&L, to-stop %, to-target %); by stock; by exit reason; **by scanner tier**; **meta-label filter** (take vs skip per model); recent trades; decision funnel (signals → intents → debates → approved → orders → fills → closed); top veto reasons; recent fills with charges.

---

## 4. Indian market adaptations (the core of this spec)

### 4.1 Instruments and segments

| Phase | Segment | Notes |
|---|---|---|
| **Phase 1 (build first)** | NSE cash equity, series `EQ`, **long only** | Delivery (`CNC`) and intraday (`MIS`). Closest analogue of the crypto spot terminal. |
| Phase 2 (optional) | Index and stock **futures** | Margin, lot sizes, expiry, rollover. Higher risk. |
| Phase 3 (strongly discouraged for automation) | Options | SEBI's own studies (2023, 2024) found roughly 9 in 10 individual F&O traders lost money. If built, analytics only (IV, Greeks, PCR, max pain); no automated option selling. |

* **Short selling:**
  * Retail can short only **intraday** in cash (MIS, auto squared-off before close).
  * Overnight shorts need SLB.
  * Phase 1 is **long-only**, like the crypto spot bot.
* **Avoid in automation:**
  * Series `BE`/`BZ` (trade-to-trade: no intraday netting).
  * Stocks under **ASM/GSM/ESM** surveillance.
  * Stocks in the **F&O ban list** (for F&O).
  * Stocks locked at upper or lower circuit.

### 4.2 Market hours and calendar (all IST)

| Session | Time | Notes |
|---|---|---|
| Pre-open | 09:00–09:15 | Order entry 09:00–09:08, matching ~09:08, buffer to 09:15. Don't trade off pre-open prints. |
| Normal market | **09:15–15:30** | Bars are only built here. |
| Closing / post-close | 15:40–16:00 | Closing price = weighted average of the last 30 minutes (NSE). VERIFY: SEBI has proposed a closing auction session that would change this. |
| Intraday square-off | Broker auto square-off of MIS ~15:15–15:25 | VERIFY per broker. The bot must flatten its own MIS positions earlier, e.g. 15:10. |
| Holidays | NSE trading-holiday list, published yearly | VERIFY each year; store as config. Special **Muhurat** session on Diwali. |

**Consequences for the code (MUST):**
* **No 24/7 market.** Every loop checks `market_open(now)`. Outside hours: no signals, no orders, scanner uses the last close.
* **Overnight gaps exist.**
  * ATR uses true range, which includes the gap from the previous close.
  * Stop-losses can gap through, so P&L simulation must fill at the open when it opens beyond the stop.
* **Replace "24h return" with "1-day / 5-day" returns.** "4h return" becomes "last 16 × 15m bars within today's session or across sessions"; document which.
* **Bars per year:**
  * 1d bars: ~248 trading days.
  * 15m bars: 25 bars per day × ~248 days.
  * Use these to annualise. Crypto used 365 days of 24 h.

### 4.3 Settlement, circuits and limits

| Rule | Value | VERIFY |
|---|---|---|
| Settlement | **T+1** for equity, since Jan 2023. A **T+0** optional segment exists for a limited list of stocks. | NSE circulars |
| Price bands (non-F&O stocks) | 2%, 5%, 10% or 20% per stock, set by the exchange | daily NSE band file |
| F&O stocks | No fixed band; dynamic price bands (flexed in steps) | NSE |
| Market-wide circuit breaker | 10%, 15%, 20% move in Nifty 50 or Sensex halts all equity trading | SEBI |
| Index derivative minimum contract value | ₹15 lakh at introduction (Nov 2024) | SEBI |
| Weekly index expiries | One weekly index expiry per exchange (Nifty weekly on NSE, Sensex weekly on BSE); expiry weekdays changed in 2025 | NSE/BSE circulars |
| Freeze quantity (F&O) | Max quantity per order; split larger orders | NSE |

The risk engine MUST:
* Refuse orders priced outside the stock's band.
* Pause on a market-wide halt.
* Never place a market order on a stock locked at a circuit.

### 4.4 Costs: the most important difference from crypto

Indian costs are **asymmetric** (some charges apply only to buys or only to sells) and include **taxes**. Model every component; this decides whether any strategy has an edge.

| Charge | Delivery (CNC) | Intraday (MIS) | Futures | Options | VERIFY |
|---|---|---|---|---|---|
| Brokerage | often ₹0 at discount brokers | lower of ₹20 / 0.03% per order (typical) | ₹20 / order typical | ₹20 / order typical | broker |
| **STT** | 0.1% on **buy and sell** | 0.025% on **sell** | 0.02% on sell (from Oct 2024) | 0.1% of premium on sell (from Oct 2024) | Finance Act / CBDT |
| Exchange transaction charge (NSE) | ~0.00297% of turnover | ~0.00297% | ~0.00173% | ~0.03503% of premium | NSE (revised Oct 2024) |
| SEBI turnover fee | ₹10 per crore | ₹10 / Cr | ₹10 / Cr | ₹10 / Cr | SEBI |
| **Stamp duty** (buy side only) | 0.015% | 0.003% | 0.002% | 0.003% | Indian Stamp Act |
| GST | 18% on (brokerage + exchange charge + SEBI fee) | same | same | same | GST |
| DP charge (sell of delivery) | ~₹13–16 + GST per stock per day | — | — | — | broker / CDSL-NSDL |

* **Implement** `charges_inr(segment, side, price, qty, broker_profile) -> dict` returning every component, unit-tested against the broker's own brokerage calculator for at least five cases.
* **Round trips:**
  * A delivery round trip costs roughly **0.22–0.25%** of trade value. STT alone is 0.2%, plus stamp, DP and exchange charges.
  * An intraday round trip costs ~0.03–0.06% plus brokerage.
  * So a 0.5% scalp target in delivery is mostly eaten by costs. Default to **intraday product for short-horizon trades and delivery for multi-day trades**, and show break-even win rate everywhere.
* **Taxes (estimate only, show as "tax estimate"):**
  * Equity **STCG** (held ≤ 12 months, STT paid): 20%.
  * **LTCG**: 12.5% on gains above ₹1.25 lakh per financial year (rates from 23 Jul 2024).
  * Intraday equity counts as speculative business income.
  * F&O counts as non-speculative business income.
  * VERIFY each Budget. P&L shows pre-tax and an estimated post-tax figure, labelled "not tax advice".

### 4.5 Brokers, APIs and data

There is **no free official real-time NSE API for individuals**. Real-time data and order placement come through a **broker API**. Build a `Broker` interface and adapters; implement one first.

```python
class Broker(Protocol):
    def login_url(self) -> str: ...                       # human completes login + 2FA in the browser
    def complete_login(self, request_token: str) -> Session: ...
    def session_valid(self) -> bool: ...                  # tokens usually expire daily (VERIFY per broker)
    def instruments(self) -> list[Instrument]: ...        # symbol, token, exchange, series, lot, tick, isin, F&O flag
    def historical(self, token, interval, start, end) -> list[Candle]: ...
    def stream(self, tokens, on_tick) -> None: ...        # WebSocket: LTP, volume, OHLC, 5-level depth, OI
    def place_order(self, req: OrderRequest) -> str: ...  # MUST attach the algo/strategy tag the broker requires
    def order_status(self, order_id) -> OrderStatus: ...
    def positions(self) -> list[Position]: ...
    def holdings(self) -> list[Holding]: ...
    def margins(self) -> Margins: ...
    def cancel_all(self) -> None: ...                     # used by the kill switch
```

| Broker API | Notes (VERIFY pricing and limits before choosing) |
|---|---|
| Zerodha **Kite Connect** | Most documented; historical data and WebSocket; daily access token; paid plans |
| **Upstox** API | Free API for customers; WebSocket; may offer a sandbox |
| Angel One **SmartAPI** | Free; TOTP-based login |
| **Fyers** API | Free for customers; WebSocket |
| **Dhan** HQ, ICICI **Breeze**, Kotak **Neo** | Alternatives |

* **Historical data for research:** use the broker's historical API. **NSE bhavcopy** (end-of-day CSV archives, including **delivery %**) is useful for daily research, but respect NSE's website terms and rate limits. Yahoo Finance tickers (`RELIANCE.NS`, `^NSEI`, `^INDIAVIX`) are acceptable only for offline prototyping: unofficial, delayed, sometimes wrong.
* **Corporate actions (MUST):**
  * Adjust history for splits and bonuses, and store raw and adjusted series.
  * Mark dividend ex-dates.
  * Exclude stocks with a split or bonus in the lookback window from intraday strategies, or adjust them.
* **Order flow:**
  * Indian feeds give LTP, volume, OHLC, 5-level depth (some give 20), total buy/sell quantity and OI.
  * There is **no taker-side flag** like Binance's `taker_buy_volume`.
  * For VPIN use **bulk volume classification**: `buy_vol = V · Φ(Δp / σ_Δp)`, with Φ the standard normal CDF; or the tick rule on ticks.
  * Book imbalance can use `total_buy_qty` vs `total_sell_qty` and 5-level depth.

### 4.6 SEBI retail algo-trading rules (VERIFY — this area changed in 2025)

* SEBI's framework for retail algorithmic trading through broker APIs (circular of Feb 2025, phased in during 2025) roughly requires:
  * API access only through the **registered broker**, with **static IP whitelisting** and OAuth-style authentication; no open APIs.
  * Orders above an **orders-per-second threshold** set by the exchange count as algo orders and need a registered **algo ID**. Below it, self-built algos for one's own account are allowed through the broker. Every API order is tagged for the audit trail.
  * Brokers act as principals for the algos on their platform.
* **The app MUST:**
  * Rate-limit itself well below the threshold (for example, at most 2 orders per second, a configurable cap per day).
  * Send whatever strategy or algo tag the broker requires on every order.
  * Run only from the whitelisted IP.
  * Log every order for audit.
* Read the latest SEBI circular and the chosen broker's API terms before enabling LIVE. If rules require registration for the intended order rate, stay in PAPER.

### 4.7 Universe and scanner (India version)

* **Universe:** all NSE `EQ`-series stocks, then filtered.
* **Exclude**, recording the reason, as in crypto:

| Reason code | Rule |
|---|---|
| `operator_excluded` | user's exclusion list in config (the crypto version excluded BTC/ETH/SOL by default; India default: none) |
| `illiquid` | median 20-day turnover < **₹25 crore** (configurable) or price < ₹50 |
| `surveillance` | in ASM / GSM / ESM lists (fetch the daily lists) |
| `trade_to_trade` | series BE/BZ |
| `circuit_locked` | at upper or lower band today |
| `wide_spread` | (ask − bid) / mid > 0.10% from 5-level depth |
| `thin_book` | ₹ value within ±0.2% of mid on the thinner side < ₹5 lakh |
| `event_risk` | results announcement or corporate action within the next 2 sessions (optional; uses the corporate-announcements calendar) |
| `spike_1d` | 1-day move > 15% (pump/dump risk) |

* **Tiers.**
  * **TREND** (daily): price > EMA50 > EMA200, RSI(14) in 45–78, drawdown from 52-week high < 25%, positive 3-month **relative strength vs Nifty 50**.
  * **SHORT_TERM** (intraday fallback): uptrend on 15m bars, RSI(15m) in 40–72, ATR(15m) in band.
  * **POTENTIAL**: best remaining movers by the short-term rank.
  * Free-fall exclusion: 1-day return ≤ −5% or last-hour return ≤ −2%.
* **Daily score** (cross-sectional z-scores):
  ```
  score = 0.45·z(momentum_3m_skip_1m) + 0.25·z(return_1w) + 0.20·z(log turnover) − 0.10·z(ATR%)
  ```
  Add **delivery %** (from bhavcopy) and **sector strength** as display columns. They join the score only after the Lab validates them.
* **Risk-off filter** (replaces "median crypto 24h ≤ −3%"): risk-off when **Nifty 50 < its 50-DMA AND India VIX > 20**, or when the advance/decline ratio < 0.5. In risk-off, only TREND-tier picks are allowed. Values are configurable.
* **Autopilot:** scan at 09:20 and every 75 minutes until 14:30. Rotate the traded list only when the fleet is flat. Log the tier of every pick to `scanner_tiers.jsonl` for the per-tier P&L split.

---

## 5. Decision stack (same as crypto; formulas to port)

### 5.1 Signal bots

* **AnalystBot:** EMA 9/21 cross and trend continuation on closed 15m bars; confidence 0.65–0.75.
* **QuantBot:** volatility regime (Garman-Klass compression ratio) + order flow (bulk-volume CVD in India).
* **LabSignalBot:** strategies promoted by the Lab gate for **this stock and this interval only** emit BUY on a fresh flat-to-long flip of the latest closed bar. Idle when nothing is promoted.

### 5.2 StrategyBot (trade construction)

* **Bracket.** Uses ATR% = ATR(14) / price from candles; never a flat guess.
  ```python
  STOP_FLOOR = 0.006            # India: raise vs crypto's 0.52% because of costs (configurable)
  def bracket(profile, atr_pct):
      if profile == "SWING":    # delivery, multi-day
          stop = max(1.5*atr_pct, STOP_FLOOR); return stop, 2*stop, horizon_days=5
      # INTRADAY: target 0.6–1.5%, must clear round-trip costs by >= 3x
      target = min(max(1.5*atr_pct, 0.006), 0.015)
      stop   = min(max(1.2*atr_pct, STOP_FLOOR), max(target, STOP_FLOOR))
      return stop, target, horizon = "until 15:10 square-off"
  ```
* **Cost check:** veto `TARGET_BELOW_COSTS` if `target_pct < 3 × round_trip_cost_pct`.
* **Features on every intent** (all known at decision time): tier, RSI(14), 1-hour and 1-day returns, EMA20/50 trend, ATR%, VPIN and its percentile, volatility regime, relative strength vs Nifty, sector, spread, depth, book imbalance, minutes to close, strategy confidence.
* **Duplicate suppression:** cooldown per symbol, plus no re-proposal on an unchanged bar.

### 5.3 DebateBot (LLM) + meta-label sidecar

* **LLM debate:**
  * Local Ollama, default model `qwen3:8b` at about 10 tok/s on a 16-core CPU; `think:false`.
  * JSON only: bull thesis, bear thesis, verdict, conviction 0–10.
  * Approve needs conviction ≥ 6.
  * Deadline 180 s; on timeout or error, **REJECT** (fail closed).
  * One debate at a time: a second arrival while busy gets `DEBATE_BUSY` and is skipped.
  * Pick an installed model automatically if the configured one is missing.
* **Meta-label** (in parallel with the debate):
  * Ask **THX-02** (HAL-X-AI/THX-02, 4.5 B decision model) and **Laya** (convaiinnovations/laya `typed-decisions`) with a text description of the trade and two questions:
    * `take` (yes/no): "will the target be hit before the stop within the time limit?"
    * `quality` (5-level score).
  * Store `thx02_p`, `laya_p`, `mean_p` on the result and journal them always.
  * RiskBot vetoes with `META_LABEL_SKIP` **only if** `META_ENFORCE=1` and `mean_p < 0.5`.
  * Start in **shadow mode**. The P&L panel recommends enforcing only after ≥ 100 judged trades, and only if "skip" trades had negative and lower expectancy than "take" trades.
* **Sidecar setup lessons:**
  * Isolated venv; CPU PyTorch from PyTorch's CPU index, with a **matching torchvision** build.
  * Load THX-02 in **bfloat16** on CPU (`THX02_CPU_DTYPE=bfloat16`); float32 needs ~18 GB RAM.
  * Load models sequentially.
  * Weights pinned to a commit hash; `HF_HUB_OFFLINE=1` at runtime.
  * Bind 127.0.0.1 only, with a bearer token.
  * On locked-down Windows (Application Control), run the sidecar inside WSL.
  * Both models are general classifiers **not trained on markets**. THX-02 visibly separated good from bad setups in tests; Laya barely did.

### 5.4 RiskBot (deterministic; no LLM)

Gates, in order (any failure gives a veto with a reason code):
1. valid prices and a protective stop;
2. debate verdict;
3. meta-label (if enforced);
4. daily new-position cap (default 8 for India; persisted per IST trading day);
5. protections (cooldown after loss, stop-loss guard, low-profit stock, closed-trade drawdown);
6. daily loss limit 2% of NAV (latching breaker);
7. max drawdown 10% (latching);
8. max open positions 3–5;
9. correlation/sector cap (≤ 2 positions per sector; static matrices are not enough — estimate rolling correlation);
10. stop distance ≥ floor;
11. **circuit-band check** (entry, stop and target all inside today's band);
12. **market-hours check** (no new MIS entry after 14:45);
13. **margin check** (from the broker in LIVE, simulated in PAPER).

**Sizing:**
```
qty = floor( (NAV · risk_fraction) / (entry − stop) )        # risk_fraction default 0.5%
cap: qty·entry ≤ min(NAV·max_order_pct(5%), per-stock cap 15% NAV − existing exposure)
then: qty ← floor(qty · m),  m = min(VPIN_toxic ? 0.5 : 1, regime HIGH ? 0.5 : EXTREME ? 0.25 : 1) ∈ [0,1]
```
Kelly sizing stays disabled until ≥ 300 closed trades.

### 5.5 ExecutionBot

* **PAPER:**
  * Fill at the next tick or bar open with slippage = max(half-spread, 0.02%).
  * Apply the full `charges_inr`.
  * Simulate stops and targets on 1-minute bars; gaps fill at the open.
  * Force square-off of MIS positions at 15:10.
* **LIVE:**
  * Limit orders by default (market only for stop exits, with market-protection %).
  * Place a **GTT** or SL order for the stop immediately after the entry fill.
  * Reconcile positions with the broker every minute.
  * Idempotent `client_order_id`.
  * Order-rate limiter (see §4.6).
* **Kill switch:** `cancel_all()`, then optionally square off, then latch.

### 5.6 Journal and P&L

* SQLite tables: `signals`, `trade_intents`, `debates`, `meta_labels`, `risk_decisions`, `orders`, `fills` (with a charges JSON), `positions_closed`, `scanner_tiers` (or JSONL).
* P&L reads them **read-only**.

---

## 6. Quant library and formulas (port unchanged unless noted)

**Volatility**

| Formula | Definition |
|---|---|
| Realised vol | stdev(log returns) · √(bars per year) |
| Parkinson | σ² = mean(ln(H/L)²) / (4 ln 2) |
| Garman-Klass | adds open/close terms to Parkinson |
| Yang-Zhang | combines overnight, open-to-close and Rogers-Satchell components; **use it in India (overnight gaps)** |
| EWMA | σₜ² = 0.94 σₜ₋₁² + 0.06 rₜ₋₁² |
| GARCH(1,1) | σₜ² = ω + α ε² + β σ² |

**Signals**

| Formula | Definition |
|---|---|
| Z-score | (x − rolling mean) / rolling stdev |
| EMA, RSI, MACD | standard definitions |
| 12-1 momentum | P(t−21) / P(t−252) − 1 on daily bars |
| ATR | mean true range (includes gaps) |
| Order-book imbalance | (Q_bid − Q_ask) / (Q_bid + Q_ask) |
| Microprice | (ask·Q_bid + bid·Q_ask) / (Q_bid + Q_ask) |

**Filters**

| Formula | Definition |
|---|---|
| t-stat | mean / (σ/√n); below 2, assume luck |
| ADF | unit-root test |
| Ornstein-Uhlenbeck half-life | −ln 2 / λ |
| Hurst exponent | R/S analysis |
| High-vol regime | σ₂₀ / σ₂₅₂ > 1.5 |

**Edge**

| Formula | Definition |
|---|---|
| Expected value | p·W − (1−p)·L |
| Break-even win rate | L / (W + L), after costs |
| Profit factor | gross win / \|gross loss\| |
| Net edge | gross − round-trip charges (India: use `charges_inr`) |

**Sizing**

| Formula | Definition |
|---|---|
| Fixed fractional | equity · risk% / \|entry − stop\| |
| Kelly | f = λ(p − (1−p)/b) |
| Volatility target | min(max lev, σ_target / σ_real) |
| Inverse-vol weights | wᵢ ∝ 1/σᵢ |

**Execution / transaction-cost analysis**

| Formula | Definition |
|---|---|
| Square-root impact | ΔP/P ≈ c·σ·√(Q/V) |
| Slippage | (fill − expected) / expected |
| VWAP / TWAP | standard definitions |
| Implementation shortfall | decision price vs average fill, including costs |

**Risk**

| Formula | Definition |
|---|---|
| Max drawdown | largest fall from a running peak |
| Recovery gain | DD / (1 − DD) |
| VaR95 | 1.645·σ·V |
| Expected shortfall | mean loss beyond VaR |
| Portfolio vol | √(wᵀΣw) |

**Validation**

| Formula | Definition |
|---|---|
| Sharpe | annualise with India bars per year |
| Sharpe t-stat | SR·√years |
| Multiple testing | 1 − (1−α)ᴺ |
| Best-of-N noise Sharpe | σ·√(2 ln N) |
| Walk-forward | rolling train/test windows |
| Monte-Carlo drawdown | shuffle trade order, read percentile max DD |

**Overfitting defences (the Lab gate)**

| Method | Definition |
|---|---|
| Triple-barrier labels | target / stop / time barrier, matching the bracket |
| CPCV | combinatorial purged cross-validation with purge and embargo |
| PBO | probability of backtest overfitting (Bailey et al.); CSCV over S blocks |
| Deflated Sharpe Ratio | adjusts for the number of trials and non-normal returns |

**Flow and regime (risk-only)**

| Formula | Definition |
|---|---|
| Bar VPIN | Σ\|buy − sell\| / ΣV over 20 bars; India uses bulk-volume classification; toxic if top-10% of own history **and** ≥ 1.5× own median → size × 0.5 |
| Volatility regime | σ(last 20) / σ(window) ≥ 1.5 HIGH (× 0.5), ≥ 2.5 EXTREME (× 0.25) |

**Factors (research)**

| Factor | Definition |
|---|---|
| Alpha158-style | rolling ROC, MA ratios, std, volume volatility, cross-sectional z-scores |
| India-specific | relative strength vs Nifty, sector momentum, delivery-% change, 52-week-high proximity |

---

## 7. Strategy Lab (India)

* **Candidates (long-only):**
  * EMA 12/26 cross; MACD + EMA100 filter; Donchian/Turtle 20-10; Bollinger reversion; RSI-2 (Connors); Supertrend 10×3; Keltner breakout; Ichimoku; time-series momentum; Williams volatility breakout; Heikin-Ashi trend; Parabolic SAR; golden cross 50/200.
  * Volatility-scaled time-series momentum; Keltner squeeze; VWAP reversion; ADX+DI; Aroon; Stoch-RSI; CCI and MFI reversion; Hull MA; KAMA; Vortex.
  * **India extras:** opening-range breakout (first 15/30 min); previous-day high breakout; 52-week-high momentum; NR7 breakout.
* **Indicator catalog:** `pandas-ta-classic` (pinned) as no-lookahead features.
* **Backtest rules:**
  * Decide at the close of bar *t* and fill at the open of *t+1*.
  * Full `charges_inr` for the chosen product.
  * No trades outside market hours.
  * Gap-aware stops.
  * Intraday strategies flat by 15:10.
* **Promotion gate (MUST, same thresholds):**
  * ≥ 100 out-of-sample trades;
  * DSR p < 0.05;
  * PBO < 0.3;
  * positive expectancy **after charges**.
  * Write passes to `promoted_strategies.json` keyed by (symbol, interval); LabSignalBot trades only those.
  * Show "0 promoted" honestly. In the crypto build, 0 of 28 passed on real data.

---

## 8. START ALL self-test (System page)

Runs checks in order, each returning `ok` / `warn` / `fail` / `skipped` with latency and detail. Critical failures block the launch steps.

| Group | Checks | Critical |
|---|---|---|
| Safety | kill switch released · risk governor · (optional) shadow risk gate | kill, governor |
| Broker | session valid, token expiry · instruments loaded · market status (open / pre-open / closed / holiday) | session (LIVE only) |
| Data | live quotes for a test stock · historical candles · scanner | data |
| Decision models | rule desk · committee · strategy library · regime model · Strategy Lab (N strategies) · promoted strategies in fleet · THX-02 + Laya sidecar · each model answers a test trade | — |
| LLMs | Ollama server · each chat model JSON ping · full debate test on the debate model (run last so it stays loaded) | Ollama, debate |
| Launch (only if no critical failed) | paper bots · autopilot + fleet · Telegram · LLM panel | — |

**Verdicts:**
* "All N models and systems are on board"
* "Partly on board: …"
* "NOT on board: <critical failures>"

The launch step refuses to switch modes while positions are open, and refuses to start while halted.

---

## 9. Suggested project layout and stack

```
zillers-india/
  app/
    dashboard/__main__.py      # stdlib ThreadingHTTPServer, routes, auth, static
    dashboard/static/*.html|js|css
    orchestrator/{engine.py, event_bus.py, events.py, base_bot.py, __main__.py}
    orchestrator/bots/{data,analyst,quant,lab_signal,strategy,debate,risk,execution,journal,notifier,supervisor}_bot.py
    broker/{base.py, kite.py | upstox.py | ...}          # adapters; secrets read here only
    market/{calendar.py (holidays, sessions), instruments.py, candle_store.py (SQLite), corporate_actions.py}
    costs/charges.py                                      # charges_inr + tax estimate (config-driven)
    desk/{scanner.py, strategy_lab.py, indicator_catalog.py, pnl.py, startup.py, paperbots.py, fleet.py}
    quant/{volatility.py, flow_risk.py, order_flow.py, sizing.py}
    core/quant/{validation.py (CPCV, PBO, DSR, triple barrier), levels/*}
    agents/{consensus.py (LLM debate), decision_models.py (meta-label client + sidecar manager)}
    models_sidecar/server.py                              # runs in its own venv
  config/india.yaml           # ALL VERIFY values: hours, holidays, charges, tax rates, bands, thresholds
  tests/                      # pytest; no network (inject fetchers); truncation tests for every indicator
  scripts/{download_decision_models.py, update_changes.py}
  docs/ALGORITHMS_AND_DECISION_ARCHITECTURE.md
  CHANGES.md                  # regenerated from git log after every commit (IST timestamps)
  .env.example                # names only, never values
```

* **Stack:**
  * Python 3.12; `numpy`, `pandas`, `scipy`, `statsmodels`, `pandas-ta-classic` (pinned).
  * No web framework needed: stdlib HTTP keeps the attack surface small.
  * SQLite.
  * Ollama for the LLM.
  * A separate venv for torch, THX-02 and Laya.
  * Pin every dependency.
* **Inject fetchers** for broker, clock and calendar so tests run offline and can simulate holidays, pre-open and circuit locks.

---

## 10. Build order with acceptance criteria

| # | Milestone | Done when |
|---|---|---|
| 1 | Config + calendar + charges | `market_open()` correct for weekdays, holidays, pre-open and Muhurat test cases; `charges_inr` matches the broker calculator on 5 delivery and 5 intraday cases to ±₹0.01 |
| 2 | Broker adapter (read-only) | Human login works; instruments, quotes, depth and history load; token expiry shown |
| 3 | Candle store + corporate actions | Adjusted and raw series; truncation tests pass |
| 4 | Dashboard shell + theme + 7 pages | Looks match §3 at 375 px and 1920 px with no horizontal scroll; ₹ in lakh/crore; IST |
| 5 | Scanner + exclusions + tiers + risk-off | Live scan shows reasons per stock; risk-off banner works with injected Nifty/VIX |
| 6 | Strategy Lab + gate | All candidates backtest net of charges; CPCV/PBO known-answer tests pass (noise gives PBO ≈ 0.5; a planted edge gives low PBO) |
| 7 | Fleet in PAPER | A replay test drives Data → … → Journal with 10+ healthy bots; MIS square-off at 15:10; no orders outside hours |
| 8 | LLM debate + meta-label sidecar | Debate fails closed; meta-label journalled in shadow; enforcement vetoes only when on |
| 9 | Risk gates + sizing | Every gate has a unit test; multipliers never exceed 1; breakers latch and persist per IST day |
| 10 | P&L page | Charges and tax-estimate columns; by tier; meta-label take-vs-skip; break-even win rate |
| 11 | START ALL | Grouped checklist; critical failures block launch |
| 12 | LIVE (last, optional) | 5 gates enforced; SEBI algo rules met (§4.6); order-rate limiter; reconciliation; kill switch cancels at the broker |

---

## 11. Honest expectations to show the user

* A Lab result of "nothing beats random after costs and multiple-testing correction" is **normal** and must be displayed, not hidden. Indian delivery costs (~0.22–0.25% round trip including STT) make short-horizon delivery trading especially hard.
* Use the P&L page's break-even win rate and the meta-label panel to decide, after **months** of paper trading, whether anything deserves real money.
* Never promise returns or set profit targets for the bots.

---

## 12. Glossary (Indian market terms)

| Term | Meaning |
|---|---|
| NSE / BSE | National Stock Exchange / Bombay Stock Exchange |
| Nifty 50 / Sensex | Main NSE / BSE indices |
| India VIX | NSE volatility index (implied, from Nifty options) |
| CNC / MIS / NRML | Delivery / intraday (auto square-off) / F&O carry-forward product types |
| GTT | Good-till-triggered order held by the broker |
| STT | Securities Transaction Tax |
| T+1 | Settlement one trading day after the trade |
| ASM / GSM / ESM | Additional / Graded / Enhanced Surveillance Measures (risky-stock lists) |
| BE / BZ series | Trade-to-trade segment (every trade settled by delivery; no intraday) |
| Bhavcopy | Exchange end-of-day price file (includes delivery quantity) |
| Upper / lower circuit | Daily price-band limit hit; trading only on one side |
| F&O ban | Stock whose open interest exceeds 95% of the market-wide position limit; no new positions |
| SLB | Securities Lending and Borrowing (needed for overnight shorts) |
| Muhurat trading | Special evening session on Diwali |

---

## 13. Official sources to VERIFY against (check before coding each rule)

* **NSE:** trading hours, holiday list, circulars, price bands, ASM/GSM lists, F&O ban list, charges, bhavcopy archives (nseindia.com).
* **BSE:** circulars, Sensex derivatives (bseindia.com).
* **SEBI:** retail algo-trading framework, F&O measures, RA/IA rules, investor studies (sebi.gov.in).
* **Income Tax Department / Union Budget:** STCG/LTCG rates, STT (incometax.gov.in).
* **Chosen broker's API docs:** login flow, token expiry, rate limits, order tags, pricing, any sandbox.
* **Broker brokerage calculator:** to unit-test `charges_inr`.
