# ⚡ ZILLER — Quantitative research, algorithmic automation, and AI-powered market intelligence

[![CI / Production Build Verification](https://github.com/ekanth14/Ziller/actions/workflows/ci.yml/badge.svg)](https://github.com/ekanth14/Ziller/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Terminal GUI](https://img.shields.io/badge/GUI-Institutional_Dark-080a0f.svg)](#)

<p align="center">
  <img src="docs/images/zillers-brand-hero.png" alt="ZILLERS — Quantitative Cryptocurrency Trading Architecture" width="100%" />
</p>

<p align="center">
  <strong>Institutional Quantitative Cryptocurrency Trading, Real-Time Market Depth & Deterministic Risk Governance</strong><br />
  <em>Conceived, engineered, and built by <strong><a href="https://github.com/ekanth14">Ekanth B S</a></strong> · Under <strong><a href="https://ziennexus.app/">Zien Organisation</a></strong></em>
</p>


> **ZILLERS** is an institutional quantitative trading, multi-source crypto market aggregation, and autonomous decision terminal engineered for 24/7 continuous digital asset markets. Built with zero unpinned external runtime dependencies, deterministic risk gating, Smart Money Concept (SMC) order block analytics, and strictly grounded local AI deliberation via Ollama.
>
> 📐 **Master Quantitative Architecture & Mathematical Specifications**: For an exhaustive, institutional breakdown of the core directory structure, technical multi-tier architecture, and all mathematical trading formulas (OLS Beta, Engle-Granger Cointegration, Ornstein-Uhlenbeck Mean Reversion, Parkinson / Garman-Klass / Yang-Zhang Volatility, CVD Order Flow, and Fractional Kelly Sizing), consult **[ZILLERS_QUANT_ARCHITECTURE.md](ZILLERS_QUANT_ARCHITECTURE.md)**.

---

## ⚠️ Regulatory & Risk Disclaimer

> **DISCLAIMER:** ZILLERS is experimental algorithmic trading software for educational and personal research use. Not investment or financial advice. Crypto assets are volatile and carry high risk of total loss.
>
> **Schedule VDA Notice:** When Indian Tax Mode is toggled, statutory deductions strictly conform to Section 115BBH (31.2% flat tax on gains without inter-asset loss set-off), Section 194S (1% TDS on gross consideration), and GST on exchange commissions. Always consult a licensed financial advisor and tax professional.

---

## 🖼️ Trading Platform Visuals & Operational Showcase

Explore the core user interface modules and telemetry dashboards engineered for ZILLERS:

### 1. Tactical Trading Terminal & Execution Workspace
High-frequency execution console featuring sub-20ms deterministic execution, aggregated multi-exchange ticker feeds, live candlestick charting, and real-time execution audit logs.

<p align="center">
  <img src="docs/images/01-tactical-trading-terminal.png" alt="ZILLERS Tactical Trading Terminal" width="100%" />
</p>

---

### 2. Level-3 Market Depth & Multi-Venue Liquidity Heatmap
Real-time streaming order book depth matrix tracking composite spread imbalances, volume profiles, and liquidity sweeps across Binance, Coinbase, and Kraken.

<p align="center">
  <img src="docs/images/02-orderbook-liquidity-heatmap.png" alt="Level-3 Market Depth & Liquidity Heatmap" width="100%" />
</p>

---

### 3. Algorithmic Strategy Engine & Smart Money Concepts
Deterministic rule evaluation engine tracking Smart Money Concepts (SMC) order blocks, Fair Value Gaps (FVG), VWAP mean reversion, and walk-forward Deflated Sharpe Ratio (DSR) model validation.

<p align="center">
  <img src="docs/images/03-algorithmic-strategy-engine.jpg" alt="Algorithmic Strategy Engine" width="100%" />
</p>

---

### 4. 5-Gate Risk Governor & Multi-Tier Emergency Kill-Switch
Fail-safe institutional risk mitigation protocol enforcing 5 mandatory gates before live execution, 3% daily maximum loss halts, 5-second feed staleness aborts, and dual-action position flattening.

<p align="center">
  <img src="docs/images/04-5gate-risk-governor-killswitch.png" alt="5-Gate Risk Governor & Kill-Switch" width="100%" />
</p>

---

### 5. Automated Bot Fleet Portfolio & Strategy Execution
Multi-strategy quantitative bot manager governing risk allocation, paper trade validation, and autonomous market execution cycles across 100+ digital asset pairs.

<p align="center">
  <img src="docs/images/05-automated-bot-fleet.png" alt="Automated Bot Fleet Portfolio" width="100%" />
</p>

---

### 6. Hardware Diagnostics & Sub-Millisecond PTP Telemetry
Hardware telemetry profiling CPU affinity pinning, zero-copy buffer allocations, and sub-millisecond event loop dispatch latency (p50: 0.089ms, p99: 0.304ms).

<p align="center">
  <img src="docs/images/06-sub-ms-performance-telemetry.png" alt="Hardware Diagnostics & Telemetry" width="100%" />
</p>

## 🏛 Core Architectural Highlights

1. **Multi-Source Market Data Aggregator (Phase 2):**
   - Real-time continuous feeds from **Binance** (`stream.binance.com`, fallback: `data-stream.binance.vision`), **Coinbase**, and **Kraken**.
   - **Median Price Calculation:** Prices cross-checked across live sources. Deviations $>1.0\%$ trigger an `UNVERIFIED` state. Single-feed status is clearly labeled `SINGLE-SOURCE` (never pseudo-verified).
   - **Per-Field Freshness Thresholds:** Live price stale after $5\text{s}$; CoinGecko metadata stale after $120\text{s}$. If feeds drop, the UI displays `Unavailable`—never placeholder or simulated numbers.
   - **Real FX Engine (Phase 3):** Real-time USD/INR rate via live currency exchange feeds with zero hardcoded seed rates; marked stale after $6\text{h}$, and the toggle automatically hides when rate is unavailable.

2. **Enterprise Authentication & Account Security (Phase 4):**
   - Password hashing with standard library `hashlib.scrypt` ($N=16384, r=8, p=1$) and 32-byte cryptographically secure salt.
   - Per-account brute-force exponential lockout (3 failures $\rightarrow$ 1m, 5 failures $\rightarrow$ 15m, 10 failures $\rightarrow$ permanent admin lock).
   - Per-IP sliding-window rate limiting ($120\text{ req/min}$ general, $12\text{ req/min}$ auth).
   - Proxy header `X-Forwarded-For` trusted only when `TRUST_PROXY=true`.
   - Fail-closed admin bootstrap: Server startup fails immediately if `ADMIN_INITIAL_PASSWORD` is unset. Forced password change on first admin login.
   - Configurable signup policy (`SIGNUP_MODE=open` or `SIGNUP_MODE=invite`).

3. **Institutional All-Coins Listings Screener (Phase 5):**
   - High-density table featuring 1h, 24h, 7d, and 30d performance, 24h volume, market cap, and 7-day SVG sparklines.
   - Cross-source price verification badges (`VERIFIED`, `SINGLE-SOURCE`, `UNVERIFIED`, `STALE`).
   - SQLite-backed per-user persistent watchlists.

4. **Fast Two-Tier Decision Layer (Phase 6):**
   - **Tier 1:** Sub-20ms deterministic execution (actual latency: p50 = 0.089ms, p99 = 0.304ms) detecting Smart Money Concepts (SMC) Order Blocks, Fair Value Gaps, liquidity sweeps, and Composite Directional Score ($-100$ to $+100$).
   - **Tier 2:** Local Laya classifier with single-thread pinning (`torch.set_num_threads(1)`), maximum 2 binary questions per setup, and a 200ms fail-safe timeout falling back to `STAND_ASIDE`.
   - **Explain Desk:** On-demand Gemma 4 explainer (`gemma4:12b`) for human operators, strictly grounded on stored facts.

5. **Realistic Crypto Backtester & Cost Model (Phase 7):**
   - Asset-class slippage (5 bps for BTC/ETH, 15 bps for altcoins) and maker/taker commissions.
   - Indian tax regime: Section 115BBH 31.2% flat tax on per-trade gains, zero loss set-off, Section 194S 1% TDS, and 18% GST on commissions.
   - Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio calculation penalizing candidate trial overfitting.
   - Schedule VDA CSV trade ledger export with statutory disclaimers.

6. **Execution Engine & 5-Gate Live Trading Multi-Governor (Phase 8):**
   - **Default is strictly `PAPER`**. Live execution cannot be enabled by default or accident.
   - **5 Mandatory Live Gates:**
     1. System environment variable `LIVE_TRADING=true`.
     2. Real exchange API credentials set in environment (`EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`).
     3. Minimum 50 closed paper trades with net-positive PnL.
     4. Admin password re-authentication within the past 5 minutes.
     5. Exact operator confirmation string `"ENABLE LIVE TRADING"`.
   - **Risk Governor:** 5% max position limit, 1.0 gross leverage limit (spot only, no shorting), max 10 open orders, 3% daily loss limit auto-halt, 5s stale feed halt, and 1.0% price divergence halt.
   - **Emergency Kill-Switch:** Master emergency kill switch canceling open orders, flattening positions, setting state to `HALTED`, and requiring admin re-auth to resume.
   - **Idempotent Exchange Adapter:** UUIDv4 client order IDs for deduplication across network retries.

---

## 📦 Installation & Quick Start

### Prerequisites
- Python 3.11 or 3.12+
- Optional: [Docker & Docker Compose](https://www.docker.com/)
- Optional: [Ollama](https://ollama.ai) with `gemma4:12b` pulled for conversational research synthesis.

### 1. Clone & Configure Environment

```bash
git clone https://github.com/ekanth14/zien-crypto-trading-software.git
cd zien-crypto-trading-software

# Copy example environment configuration
cp .env.example .env
```

Edit `.env` and set your initial admin password:
```env
ADMIN_INITIAL_PASSWORD=MySecureAdminPassword2026!
PORT=8900
HOST=127.0.0.1
```

### 2. Run with Native Python

```bash
# Launch terminal server
python -m cryptoscope.dashboard --port 8900
```

Open your browser and navigate to:
```
http://localhost:8900
```

### 3. Run with Docker Compose

```bash
docker compose up --build -d
```

The containerized terminal will run on port `8900` as a non-root user with automatic volume persistence for `data/`.

---

## ⚙️ Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ADMIN_INITIAL_PASSWORD` | **Required** | Startup fails if unset. Initial password for `admin@zillers.local`. |
| `PORT` | `8900` | HTTP listening port. |
| `HOST` | `127.0.0.1` | Network interface binding. |
| `TRUST_PROXY` | `false` | Set to `true` only when running behind trusted reverse proxies (e.g. Nginx). |
| `SIGNUP_MODE` | `open` | Set to `invite` to restrict new registrations to invite codes. |
| `INVITE_CODE` | `ZILLERS-INVITE-2026` | Required registration code if `SIGNUP_MODE=invite`. |
| `LIVE_TRADING` | `false` | Gate 1 flag for live trading. Must be explicitly set to `true` to enable live execution. |
| `EXCHANGE_API_KEY` | `""` | Exchange API key for live execution (withdrawal permissions MUST be disabled). |
| `EXCHANGE_API_SECRET` | `""` | Exchange API secret. |
| `MAX_POSITION_PCT` | `0.05` | Maximum portfolio allocation per single position (5%). |
| `MAX_GROSS_LEVERAGE` | `1.0` | Maximum gross leverage (strictly 1.0 for spot-only trading). |
| `MAX_DAILY_LOSS_PCT` | `0.03` | Maximum daily portfolio drawdown before triggering emergency halt (3%). |
| `MAX_OPEN_ORDERS` | `10` | Maximum concurrent open orders permitted. |
| `DEVIATION_THRESHOLD_PCT` | `1.0` | Maximum cross-exchange price divergence before marking `UNVERIFIED`. |
| `TICKER_STALE_SECONDS` | `5.0` | Live ticker freshness window. |
| `METADATA_STALE_SECONDS` | `120.0` | CoinGecko metadata caching TTL. |
| `FX_STALE_SECONDS` | `21600` | FX rate expiration window (6 hours). |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API endpoint. |
| `OLLAMA_MODEL` | `gemma4:12b` | Pinned LLM model name. |

---

## 📡 Public Market Data Attributions & Licensing

- **CoinGecko:** Public market cap rankings, 24h volumes, and 7-day sparklines provided by [CoinGecko Public API](https://www.coingecko.com/en/api). Respects terms of use, public rate limits, and attribution guidelines.
- **Binance:** Real-time ticker and kline WebSocket streams provided by [Binance Public API](https://binance-docs.github.io/apidocs/spot/en/) and [Binance Vision Fallback](https://data-stream.binance.vision).
- **Coinbase:** Market quote feeds provided by [Coinbase Developer Exchange API](https://docs.cdp.coinbase.com/).
- **Kraken:** Real-time WebSocket public quote and trade feeds.

---

## 🧪 Testing & Verification

Run the full pytest suite:

```bash
pytest -v
```

Or via unittest runner:

```bash
python -m unittest discover -s cryptoscope/tests -p "test_*.py"
```

The 108 test cases cover:
- `test_governor.py`: 5-gate live trading governor, emergency kill switch, risk limits, stale feed halts, cross-feed divergence halts.
- `test_backtest_costs.py`: Slippage, maker/taker fees, Indian tax model (Section 115BBH & 194S), Deflated Sharpe Ratio, Schedule VDA CSV export.
- `test_fx.py`: Real FX rate fetching, unavailable state handling, staleness transitions.
- `test_market_data.py`: Multi-source median aggregator, divergence detection, fallback connections, WAL candle store.
- `test_auth.py`: Scrypt hashing, account lockout backoff, rate limiter, admin bootstrapping, CSRF validation.
- `test_dashboard.py`: Route handlers, live data feeds, feature catalogs.
- `test_autotrader.py`: Pre-trade risk gates, order block detection, autonomous cycle evaluation.

---

---

## 🤝 Research Collaboration & Submissions Desk

ZILLERS is engineered in the open under [Zien Organisation](https://ziennexus.app/). Quantitative researchers, machine learning engineers, and algorithmic traders can propose models, academic paper implementations, and strategy integrations:

- **Web Showcase Form:** Navigate to `http://localhost:8900/landing/#collaborate`
- **Submissions Desk UI:** Browse and filter all received proposals at `http://localhost:8900/collaborations`
- **REST API:** `GET /api/collaborate/list` (or `/api/collaborate`)
- **CLI Submissions Viewer:**
  ```bash
  python scripts/view_collaborations.py
  ```
- **Local Storage:** All verified proposals are logged to `data/collaborations.json`.

## 📄 License

This software is released under the [MIT License](LICENSE).