# ZILLERS Quant Institutional Terminal

[![CI / Production Build Verification](https://github.com/ekanth14/zien-crypto-trading-software/actions/workflows/ci.yml/badge.svg)](https://github.com/ekanth14/zien-crypto-trading-software/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Terminal GUI](https://img.shields.io/badge/GUI-Institutional_Dark-080a0f.svg)](#)

> **ZILLERS** is an institutional quantitative trading, multi-source crypto market aggregation, and autonomous decision terminal engineered for 24/7 continuous digital asset markets. Built with zero unpinned external runtime dependencies, deterministic risk gating, Smart Money Concept (SMC) order block analytics, and strictly grounded local AI deliberation via Ollama.

---

## ⚠️ Regulatory Disclaimer

> **NOT FINANCIAL ADVICE:** ZILLERS is a software research, market data aggregation, and autonomous paper execution platform. Cryptographic assets involve substantial market risk, structural volatility, and liquidity slippage. Historical backtests, statistical quant signals, and AI copilots do not guarantee future investment returns. Always conduct independent due diligence.

---

## 🏛 Core Architectural Highlights

1. **Multi-Source Market Data Aggregator:**
   - Real-time continuous feeds from **Binance** (`stream.binance.com`, fallback: `data-stream.binance.vision`) and **Coinbase**.
   - **Median Price Calculation:** Prices cross-checked across live sources. Deviations $>1.0\%$ trigger an `UNVERIFIED` state. Single-feed status is clearly labeled `SINGLE-SOURCE` (never pseudo-verified).
   - **Per-Field Freshness Thresholds:** Live price stale after $5\text{s}$; CoinGecko metadata stale after $120\text{s}$. If feeds drop, the UI displays `Unavailable`—never placeholder or simulated numbers.
   - **Real FX Engine:** Real-time USD/INR rate via live currency exchange feeds with zero hardcoded seed rates; marked stale after $6\text{h}$, and the toggle automatically hides when rate is unavailable.

2. **Smart Money Concepts (SMC) & Institutional Alpha:**
   - Automated detection of Bullish and Bearish Order Blocks with volume imbalance confirmation.
   - Composite Directional Score ($-100$ to $+100$) integrating Wilder RSI (14), EMA Trend (20/50/200), and Volume Delta.
   - Strict Pre-Trade Risk:Reward Gatekeeper enforcing $R:R \ge 1.50:1$ calculated via Wilder ATR (14).

3. **Enterprise Authentication & Account Security:**
   - Password hashing with standard library `hashlib.scrypt` ($N=16384, r=8, p=1$).
   - Per-account brute-force lockout (5 consecutive failed attempts $\rightarrow$ 15-minute lock).
   - Per-IP sliding-window rate limiting ($120\text{ req/min}$ general, $12\text{ req/min}$ auth).
   - Proxy header `X-Forwarded-For` trusted only when `TRUST_PROXY=true`.
   - Fail-closed admin bootstrap: Server startup fails immediately if `ADMIN_INITIAL_PASSWORD` is unset. Forced password change on first admin login.
   - Configurable signup policy (`SIGNUP_MODE=open` or `SIGNUP_MODE=invite`).

4. **Strictly Grounded Laya AI Copilot:**
   - Pinned strictly to `gemma4:12b` via Ollama.
   - Grounding validator strictly rejects any hallucinated or unverified numbers not present in the verifiable snapshot or database. Zero synthetic fallbacks.

---

## 📦 Installation & Quick Start

### Prerequisites
- Python 3.11 or 3.12+
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
docker-compose up --build -d
```

The containerized terminal will run on port `8900` with automatic volume persistence for `data/`.

---

## ⚙️ Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `ADMIN_INITIAL_PASSWORD` | **Required** | Startup fails if unset. Initial password for `admin@zillers.local`. |
| `PORT` | `8900` | HTTP listening port. |
| `HOST` | `127.0.0.1` | Network interface binding. |
| `TRUST_PROXY` | `false` | Set to `true` only when running behind trusted reverse proxies (e.g. Nginx). |
| `SIGNUP_MODE` | `open` | Set to `invite` to restrict new registrations to invite codes. |
| `INVITE_CODE` | `ZILLERS-2026` | Required registration code if `SIGNUP_MODE=invite`. |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API endpoint. |
| `OLLAMA_MODEL` | `gemma4:12b` | Pinned LLM model name. |
| `DEVIATION_THRESHOLD_PCT` | `1.0` | Maximum cross-exchange price divergence before marking `UNVERIFIED`. |
| `TICKER_STALE_SECONDS` | `5.0` | Live ticker freshness window. |
| `METADATA_STALE_SECONDS` | `120.0` | CoinGecko metadata caching TTL. |
| `FX_STALE_SECONDS` | `21600` | FX rate expiration window (6 hours). |

---

## 📡 Public Market Data Attributions & Licensing

- **CoinGecko:** Public market cap rankings, 24h volumes, and 7-day sparklines provided by [CoinGecko Public API](https://www.coingecko.com/en/api). Respects terms of use, public rate limits, and attribution guidelines.
- **Binance:** Real-time ticker and kline WebSocket streams provided by [Binance Public API](https://binance-docs.github.io/apidocs/spot/en/) and [Binance Vision Fallback](https://data-stream.binance.vision).
- **Coinbase:** Market quote feeds provided by [Coinbase Developer Exchange API](https://docs.cdp.coinbase.com/).

---

## 🧪 Testing & Verification

Run the full pytest suite:

```bash
python -m pytest -v
```

The test suite covers:
- `test_fx.py`: Real FX rate fetching, unavailable state handling, staleness transitions.
- `test_market_data.py`: Multi-source median aggregator, divergence detection, fallback connections, WAL candle store.
- `test_auth.py`: Scrypt hashing, account lockout backoff, rate limiter, admin bootstrapping, CSRF validation.
- `test_dashboard.py`: Route handlers, live data feeds, feature catalogs.
- `test_autotrader.py`: Pre-trade risk gates, order block detection, autonomous cycle evaluation.

---

## 📄 License

This software is released under the [MIT License](LICENSE).
