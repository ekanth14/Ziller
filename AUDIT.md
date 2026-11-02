# ZILLERS Production Hardening — Phase 0 Baseline & Security Audit

**Document Date**: 2026-11-02  
**Target Package**: `cryptoscope/`  
**Git Branch**: `prod-hardening` (branched from `main` @ `3429e2d`)  
**Auditor**: Senior Quantitative-Systems Engineer & QA Lead  
**Status**: Baseline Completed — Zero Code Changes in Phase 0

---

## 1. Test Suite Baseline & Gap Analysis

The test suite was executed in the clean production virtual environment with `pytest cryptoscope/tests -v`.

### Execution Summary
- **Collected**: 170 test items
- **Passed**: 163 tests
- **Failed**: 0 tests
- **Skipped**: 7 tests
- **Subtests Passed**: 31 subtests
- **Duration**: 24.59 seconds

### Explanation of the 7 Skipped Tests
The 7 skipped tests correspond exclusively to the optional `quantjourney-bt` standalone backtesting engine, which is pinned in `requirements-backtest.txt` for historical research backtests. In the production terminal runtime, standard backtesting uses the stdlib/NumPy deterministic baseline engine:
1. `cryptoscope/tests/test_feature_integration.py:70`
2. `cryptoscope/tests/test_feature_integration.py:81`
3. `cryptoscope/tests/test_feature_integration.py:93`
4. `cryptoscope/tests/test_feature_integration.py:105`
5. `cryptoscope/tests/test_repository_extensions.py:134`
6. `cryptoscope/tests/test_repository_extensions.py:153`
7. `cryptoscope/tests/test_repository_extensions.py:161`

All other 163 tests pass with 100% success across auth, autotrader, risk governors, market feeds, quant algorithms, and live terminal E2E.

---

## 2. Comprehensive Endpoint Matrix

### A. The 16 Routes Specified in Architectural Documentation

| # | Spec Route | Method | Exists in Server | Called by app.js | Request Schema | Response Schema | Auth Requirement |
|---|---|---|---|---|---|---|---|
| 1 | `/api/market/tickers` | `GET` | **Yes** | **Yes** | None | `{"tickers": [{"symbol": str, "price": float, ...}]}` | Public |
| 2 | `/api/market/candles` | `GET` | **Yes** | **Yes** | Query: `symbol`, `interval`, `limit` | `{"symbol": str, "candles": [...], "count": int}` | Public |
| 3 | `/api/market/stream` | `GET` | **Yes** | **Yes** | None (SSE text/event-stream) | SSE `data: {"tickers": [...], "connections": {...}}` | Public |
| 4 | `/api/market/listings` | `GET` | **Yes** | **Yes** | Query: `page`, `per_page` | `{"items": [{"id": str, "symbol": str, "price_usd": float, "change_24h_pct": float, ...}], "total": int}` | Public |
| 5 | `/api/quant/pairs` | `GET` | **Yes** | **Yes** | Query: `pairs` (e.g. `ETHUSDT:BTCUSDT`) | `{"pairs": [{"pair": str, "beta": float, "half_life": float, "zscore": float, "signal": str, "action": str}], "as_of": float}` | Public |
| 6 | `/api/quant/volatility` | `GET` | **Yes** | **Yes** | Query: `symbol`, `interval` | `{"status": str, "regime": str, "compression_ratio": float, "breakout_readiness_pct": float, "estimators": {...}}` | Public |
| 7 | `/api/quant/orderflow` | `GET` | **Yes** | **Yes** | Query: `symbol`, `lookback` | `{"status": str, "buy_volume_ratio": float, "taker_dominance": str, "divergence": {...}}` | Public |
| 8 | `/api/quant/sizing` | `POST` | **Yes** | **Yes** | JSON: `{account_balance, entry_price, stop_loss, win_rate, win_loss_ratio, kelly_fraction, max_account_risk_pct}` | `{"status": str, "position_size_usd": float, "position_qty": float, "risk_usd": float, "kelly_metrics": {...}}` | Public *(Rate limit recommended)* |
| 9 | `/api/market/simulate_odds` | `POST` | **Yes** | **Yes** | JSON: `{symbol, entry, stop, target, horizon_bars, replays}` | `{"symbol": str, "p_target": float, "p_stop": float, "p_timeout": float, "ev_r": float, "edge": str, "sim_paths": int}` | Public *(Rate limit recommended)* |
| 10 | `/api/agents/deliberate` | `POST` | **Yes** | **Yes** | JSON: `{symbol, balance}` | `{"symbol": str, "action": str, "conviction_score": int, "bull_thesis": str, "bear_thesis": str, "risk_debate": str}` | Public *(Rate limit recommended)* |
| 11 | `/api/risk/token_audit` | `POST` | **Yes** | **Yes** | JSON: `{symbol, float_tokens, reserve_tokens, liquidity_usd}` | `{"symbol": str, "score": int, "band": str, "operators": [...], "guard": {...}}` | Public *(Rate limit recommended)* |
| 12 | `/api/governor/status` | `GET` | **Yes** | **Yes** | None | `{"mode": str, "kill_switch_engaged": bool, "action": str, "emergency_halted": bool, "target_exchange": str}` | Public |
| 13 | `/api/governor/kill_switch` | `POST` | **Yes** | **Yes** | JSON: `{action: "HALT" \| "HALT_FLATTEN", csrf_token}` | `{"status": "ok", "action": str, "halted_at": float, "halted_by": str}` | Session Cookie + CSRF |
| 14 | `/api/governor/resume` | `POST` | **Yes** | **Yes** | JSON: `{password: str, csrf_token}` | `{"status": "ok", "resumed_by": str, "resumed_at": float}` | Admin Password + Session Cookie + CSRF |
| 15 | `/api/governor/live_toggle` | `POST` | **Yes** | **No** (Direct UI modal pending) | JSON: `{mode: "LIVE" \| "PAPER", password: str, confirmation: str, paper_trades_count: int, paper_net_pnl: float, csrf_token}` | `{"status": "ok", "mode": "LIVE" \| "PAPER"}` | Admin Password + Session Cookie + CSRF |
| 16 | `/api/auth/login` | `POST` | **Yes** | **Yes** | JSON: `{email: str, password: str}` | `{"status": "ok", "user": {...}, "csrf_token": str}` + `Set-Cookie: session_token=...` | Public (Rate-limited, Account Lockout) |

---

### B. Additional Routes Found in Server Code (Not in Spec List)

| Route | Method | Exists in Server | Called by app.js | Purpose | Auth Requirement |
|---|---|---|---|---|---|
| `/api/auth/signup` | `POST` | **Yes** | **Yes** | Create user account (when `SIGNUP_MODE=open` or with invite code) | Public (Rate-limited) |
| `/api/auth/logout` | `POST` | **Yes** | **Yes** | Revoke session and clear cookie | Public / Session Cookie |
| `/api/auth/me` | `GET` | **Yes** | **Yes** | Inspect active session user details & CSRF token | Session Cookie |
| `/api/auth/reauth` | `POST` | **Yes** | **No** | 5-minute elevated session elevation | Session Cookie + Password |
| `/api/auth/reset_password` | `POST` | **Yes** | **Yes** | Request password reset token | Public (Rate-limited) |
| `/api/auth/confirm_reset` | `POST` | **Yes** | **Yes** | Submit new password with reset token | Public |
| `/api/auth/change_password` | `POST` | **Yes** | **No** | Mutate password within active session | Session Cookie + CSRF |
| `/api/fx/rate` | `GET` | **Yes** | **Yes** | Real-time USD/INR FX conversion rate | Public |
| `/api/market/ticker` | `GET` | **Yes** | **Yes** | Single ticker quote fallback | Public |
| `/api/market/connections` | `GET` | **Yes** | **No** | Diagnostic connection status across feeds | Public |
| `/api/laya/status` | `GET` | **Yes** | **Yes** | Operational diagnostics of Laya Tier-2 engine | Public |
| `/api/dashboard` | `GET` | **Yes** | **Yes** | Tactical workspace summary | Public / Workspace param |
| `/api/features` | `GET` | **Yes** | **Yes** | Feature repository catalog | Public |
| `/api/autotrader` | `GET` | **Yes** | **Yes** | Autonomous engine operational status & metrics | Public |
| `/api/autotrader/runs/*` | `GET` | **Yes** | **Yes** | Inspect historical autonomous decision artifact | Public |
| `/api/forecasts/*` | `GET` | **Yes** | **Yes** | Inspect deep learning forecast artifact | Public |
| `/api/strategies/*` | `GET` | **Yes** | **Yes** | Inspect strategy studio artifact | Public |
| `/api/backtests/*` | `GET` | **Yes** | **Yes** | Inspect strategy backtest report | Public |
| `/api/runs/*` | `GET` | **Yes** | **Yes** | Inspect research run details | Public |
| `/api/user/favorites` | `GET` | **Yes** | **Yes** | Fetch user starred crypto symbols | Session Cookie |
| `/api/user/favorites/toggle` | `POST` | **Yes** | **Yes** | Toggle starred crypto symbol | Session Cookie + CSRF |
| `/api/user/settings` | `GET` / `POST` | **Yes** | **No** | Get/set display currency and theme | Session Cookie + CSRF |
| `/api/collaborate` | `GET` / `POST` | **Yes** | **No** | Submit or list institutional collaboration proposals | Passcode gated for list |
| `/api/collaborate/auth` | `POST` | **Yes** | **No** | Operator passcode auth for collaboration submissions | Passcode gated |
| `/health` | `GET` | **Yes** | **No** | Liveness probe endpoint (`status: healthy`) | Public |
| `/ready` | `GET` | **Yes** | **No** | Readiness probe endpoint (`status: ready`) | Public |

---

## 3. Environment Variables Audit

Every environment variable accessed across the codebase:

| Variable | File Location | Purpose | Default Value / Behavior | Security Risk & Recommendation |
|---|---|---|---|---|
| `ADMIN_INITIAL_PASSWORD` | `cryptoscope/auth/store.py` | Initial bootstrap password for `admin@zillers.local` | None (Raises ValueError if unset when initializing DB) | **CRITICAL**: Must never be hardcoded or documented as plain text. Ensure it is set only via secure `.env`. |
| `COLLAB_DESK_PASSCODE` | `cryptoscope/dashboard/__main__.py` | Operator passcode for `/collaborate/submissions` | `"Ekanthbs@4514"` | **HIGH RISK**: Hardcoded plain-text personal password in source code! Must be moved strictly to env var with no hardcoded fallback. |
| `EXCHANGE_API_KEY` | `cryptoscope/execution/governor.py` | Binance API Key | `""` | Safe: Defaults to empty string. |
| `EXCHANGE_API_SECRET` | `cryptoscope/execution/governor.py` | Binance API Secret | `""` | Safe: Defaults to empty string. |
| `LIVE_TRADING` | `cryptoscope/execution/governor.py` | Binary switch allowing live routing | `"0"` (Disabled) | Safe: Defaults closed to paper mode. |
| `ALERT_EMAIL` | `cryptoscope/execution/governor.py` | Risk alert dispatch email | `""` | Informational. |
| `TELEGRAM_BOT_TOKEN` | `cryptoscope/execution/governor.py`, `notifier.py` | Telegram alert bot token | `""` | Safe: Defaults to empty string. |
| `TELEGRAM_CHAT_ID` | `cryptoscope/execution/governor.py`, `notifier.py` | Telegram alert chat ID | `""` | Safe: Defaults to empty string. |
| `DISCORD_WEBHOOK_URL` | `cryptoscope/autotrader/notifier.py` | Discord alert webhook | `""` | Safe: Defaults to empty string. |
| `GENERIC_WEBHOOK_URL` | `cryptoscope/autotrader/notifier.py` | Generic HTTP notification endpoint | `""` | Safe: Defaults to empty string. |
| `INVITE_CODE` | `cryptoscope/auth/store.py` | Mandatory invite code for signup | `None` | Safe: If set, enforces invite-only registration. |
| `SIGNUP_MODE` | `cryptoscope/auth/store.py` | Registration mode (`closed`, `open`, `invite_only`) | `"closed"` | Safe: Default closed. |
| `SCRYPT_MAX_CONCURRENT` | `cryptoscope/auth/security.py` | Semaphore limit on parallel scrypt hash calculations | `3` | Safe: Prevents CPU exhaustion via parallel login brute forcing. |
| `TRUST_PROXY` | `cryptoscope/auth/security.py` | Whether to trust `X-Forwarded-For` header for client IP | `"0"` | Safe: Refuses proxy spoofing by default. |
| `LAYA_THREADS` | `cryptoscope/autotrader/decision.py` | PyTorch / Laya thread pinning count | `1` | Safe: Avoids multi-core thrashing. |
| `LAYA_TIMEOUT_MS` | `cryptoscope/autotrader/decision.py` | Strict timeout budget for Tier-2 inference | `200.0` ms | Safe: Enforces fail-closed on timeout. |
| `OLLAMA_HOST` | `cryptoscope/autotrader/decision.py`, `laya.py` | URL for local Ollama instance | `http://127.0.0.1:11434` | Safe: Default localhost only. |
| `OLLAMA_MODEL` | `cryptoscope/autotrader/decision.py`, `laya.py` | Local model name for multi-agent debate | `gemma4:12b` | Informational. |
| `GATE3_MIN_PAPER_TRADES` | `cryptoscope/execution/governor.py` | Minimum paper trades before Gate 3 live pass | `20` | Safe: Hard risk constraint. |
| `GATE3_MIN_FORWARD_DAYS` | `cryptoscope/execution/governor.py` | Minimum forward paper trading days | `7` | Safe: Prevents premature activation. |
| `GATE3_MIN_DSR` | `cryptoscope/execution/governor.py` | Minimum Deflated Sharpe Ratio | `0.95` | Safe: Statistical validation constraint. |
| `GATE3_MAX_DRAWDOWN_LIMIT`| `cryptoscope/execution/governor.py` | Maximum tolerable paper drawdown | `0.05` (5%) | Safe: Hard risk constraint. |
| `USERPROFILE` | `cryptoscope/autotrader/decision.py` | Windows home path for `.laya` checkpoints | Standard Windows OS env var | Standard OS fallback. |

---

## 4. External Services & Endpoints Audit

All external network interactions in the application:

1. **Binance Spot Exchange Feeds**:
   - `https://api.binance.com/api/v3` (REST market data & snapshot candles)
   - `wss://stream.binance.com:9443/ws` (WebSocket live ticker and depth stream)
   - `https://testnet.binance.vision/api` (Binance Spot Testnet API for risk testing)
   - `https://data-api.binance.vision` (Binance public archive fallback)
2. **Coinbase Advanced Trade Feed**:
   - `https://api.exchange.coinbase.com` (REST ticker)
   - `wss://ws-feed.exchange.coinbase.com` (WebSocket ticker channel)
3. **Kraken Spot Feed**:
   - `https://api.kraken.com/0/public` (REST ticker)
   - `wss://ws.kraken.com` (WebSocket ticker channel)
4. **CoinGecko**:
   - `https://api.coingecko.com/api/v3` (Top 100 cryptocurrency metadata & listings)
5. **Open Exchange Rates**:
   - `https://open.er-api.com/v6/latest/USD` (USD / INR real-time exchange rates)
6. **Local Ollama Daemon**:
   - `http://127.0.0.1:11434` (Local gemma4:12b inference for research debate agents)
7. **Telegram Bot API**:
   - `https://api.telegram.org/bot<TOKEN>/sendMessage` (Emergency kill-switch & risk alerts)

---

## 5. Hardcoded Paths, URLs & CDNs Audit

1. **Content Security Policy (CSP) CDN Reference**:
   - In `cryptoscope/dashboard/__main__.py`: Header `Content-Security-Policy` contains `script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com;`.
   - **Defect**: Tailwind CDN is referenced in headers, conflicting with the "no external layout CDNs" rule.
2. **Hardcoded Passcode in Server**:
   - In `cryptoscope/dashboard/__main__.py:40`: `COLLAB_DESK_PASSCODE = os.environ.get("COLLAB_DESK_PASSCODE", "Ekanthbs@4514")`.
   - **Defect**: Violates zero-hardcoded-credentials rule.
3. **Admin Password in Documentation & Tests**:
   - `README.md` and `ZILLERS_QUANT_ARCHITECTURE.md` documented bootstrap admin credentials `admin@zillers.local` / `AdminTestingPassword123!`.
   - `test_server_endpoints.py` relies on `AdminTestingPassword123!`.
   - **Defect**: Violates production security rules; server must strictly require env var `ADMIN_INITIAL_PASSWORD`.
4. **Local Windows `file:///` Absolute Links**:
   - In `ZILLERS_QUANT_ARCHITECTURE.md`, markdown links point to `file:///c:/Users/Ekanth...`.
   - **Defect**: Non-portable across Linux/macOS and other developer machines. Should be standard repository relative links.

---

## 6. Phase 0 Audit Conclusion & Action Plan for Phase 1

The baseline is verified with **163 passed / 0 failed / 7 skipped**.
We now advance directly to **Phase 1: Fix Backend-Frontend Integration**:
1. Fix CSP headers in `__main__.py` to remove `https://cdn.tailwindcss.com`.
2. Add rate limiting, payload validation, and max size constraints to public POST routes (`/api/quant/sizing`, `/api/market/simulate_odds`, `/api/agents/deliberate`, `/api/risk/token_audit`).
3. Verify and harden SSE `/api/market/stream` thread cleanup, disconnect handling, and client reconnection backoff.
4. Verify complete CSRF, HttpOnly, and SameSite enforcement on all mutating authenticated routes.
5. Ensure empty, loading, error, and "feed unavailable" (`—`) states across every UI component with zero console errors.
