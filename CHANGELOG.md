# Changelog

All notable changes to the ZILLERS Quant Institutional Terminal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0-crypto] - 2026-11-01

### Added
- **Full Crypto Transformation:** Removed all legacy NSE/BSE equities, Indian stock market trading hours (09:15-15:30), circuit limits, and mock seed tickers. Replaced with continuous 24/7/365 rolling crypto markets.
- **Multi-Source Market Data Aggregator (`cryptoscope/market_data/`):**
  - Live public market streams from Binance (with automatic fallback to `data-stream.binance.vision`) and Coinbase.
  - Multi-source median price calculation across active fresh feeds.
  - Automatic cross-source deviation tracking (divergence $>1.0\%$ triggers `UNVERIFIED`).
  - Single-feed state labeled as `SINGLE-SOURCE` (truthfulness rule: never marked verified if only 1 source is alive).
  - Per-field freshness thresholds (5s for live ticks, 120s for CoinGecko metadata).
  - SQLite WAL-backed time-series `CandleStore` for persistent kline storage.
- **Real-Time FX Engine (`cryptoscope/fx/`):**
  - Zero hardcoded seed rates; returns `status: "unavailable"` until live network fetch succeeds.
  - Auto-hides currency toggle when unavailable; marks rate stale after 6 hours.
- **Enterprise Authentication & Security System (`cryptoscope/auth/`):**
  - High-security password hashing using `hashlib.scrypt` ($N=16384, r=8, p=1$).
  - Per-account lockout (5 consecutive failed attempts $\rightarrow$ 15-minute lock).
  - Sliding-window rate limiter per client IP.
  - Proxy header `X-Forwarded-For` trusted only when `TRUST_PROXY=true`.
  - Fail-closed admin bootstrap requiring `ADMIN_INITIAL_PASSWORD` with mandatory first-login password change.
  - Configurable registration modes (`open` vs. `invite`).
  - Password reset tokens with logging fallback.
- **All Crypto Listings Screener (Dashboard UI):**
  - Live screener for 100+ digital assets powered by CoinGecko public API with SVG 7-day sparklines.
  - Real-time tick flashing on price updates (bull green / bear rose).
  - Per-user favorite watchlists synchronized via SQLite store.
  - Asset modal inspector displaying live cross-source prices, SMC order blocks, and directional scores.
- **ICT Smart Money Concepts (SMC) & Alpha Engine:**
  - Automated detection of Bullish and Bearish Order Blocks.
  - Composite Directional Score ($-100$ to $+100$) combining Wilder RSI (14), EMA Trend, and Volume Delta.
  - Dynamic Wilder ATR risk targets ($R:R \ge 1.50:1$).
- **Grounded Laya AI Copilot:**
  - Pinned strictly to `gemma4:12b` via Ollama.
  - Grounding validator enforcing zero invented metrics; responses must strictly cite verified numbers from context.
- **Production Readiness & DevOps:**
  - Containerization with multi-stage `Dockerfile` and `docker-compose.yml`.
  - Comprehensive `.github/workflows/ci.yml` matrix testing across Ubuntu and Windows runners.
  - Enforced `.gitignore` ensuring zero database files (`*.db`, `*.sqlite3`) or `.env` files are tracked.
  - Institutional "Not Financial Advice" regulatory disclaimer banner.
