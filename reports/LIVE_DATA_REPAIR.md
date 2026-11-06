# Live-data entry-point and freshness repair

November 6, Asia/Calcutta. User reported unavailable live data and asked to continue the repair.

## Reproduced cause

Read-only checks showed localhost:8900 served the old disposable preview: all eight tickers unavailable and all sources offline. The real workspace server on 8910 had eight fresh quotes with BTC/ETH/SOL verified across Binance, Coinbase and Kraken. Redirecting the user to another port had left the original entry point broken.

The two dashboard processes created earlier in this chat were identified through their saved PID files, executable paths and dashboard module command lines. Only those processes were terminated through Windows process management. No trading bot was terminated. The workspace dashboard now runs at http://localhost:8900/; `python -B scripts/run_dashboard.py` uses that port by default again.

## Code repairs

- Connecting the SSE socket alone no longer labels the feed live. Status depends on a positive, finite, fresh quote for the selected symbol. Single-source and price-disagreement states are distinguished.
- Receipt time is tracked alongside server quote age. The page expires old quotes even if the stream stops sending new messages. Metadata prices do not become live quotes.
- Chart redraws preserve the fresh headline quote rather than replacing it every refresh with the last closed candle. The candle timestamp is labeled Last closed bar.
- The order book no longer falls back to archived bot quotes or displays expired quotes as current.
- The Binance poll loop now treats a whole cycle with no quotes as a failure, allowing its existing endpoint fallback to activate. Previously individual fetch failures returned None and the loop reset its failure counter regardless.

## Observed verification

- `python -B scripts/run_isolated_tests.py cryptoscope/tests/test_market_data.py cryptoscope/tests/test_server_endpoints.py cryptoscope/tests/test_dashboard.py cryptoscope/tests/test_dashboard_startup.py`: 47 passed, exit 0, 14.06 seconds. Disposable evidence: C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-7x70yfp8.
- `node --test cryptoscope/tests/test_live_feed.cjs`: six tests passed. Covers fresh quotes, expiry without new stream messages, stale server status, missing values, metadata provenance and single-source validity.
- `node --check cryptoscope/dashboard/static/app.js`: passed. `git diff --check`: passed.
- Real GET to /api/market/stream on port 8900: three consecutive frames, increasing timestamps, fresh prices for BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT and AVAXUSDT.
- Installed headless Chromium loaded the actual page on port 8900. It showed LIVE STREAMING and a current ETH quote, with zero JavaScript page errors. The chart timestamp said Last closed bar, and the emergency halt remained engaged. Screenshot retained locally at work/runtime/live-data-fixed.png.
- The initial browser test predicate used string evaluation, which the existing CSP rejected. The observer was corrected to use DOM locators; CSP was not relaxed.

## Boundaries

Public market feeds are online. Live or testnet order execution was not enabled or called. No account reset, database/file deletion, production environment-file edit, governor-policy change or model generation occurred. Phase 2 research results and its documented limits remain unchanged.
