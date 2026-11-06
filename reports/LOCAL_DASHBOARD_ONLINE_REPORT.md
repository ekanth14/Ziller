# Online localhost dashboard repair

November 6, Asia/Calcutta. User explicitly requested a working online dashboard and fixes. This expands the prior isolated-preview scope to public online market data; trading remains halted.

Working URL: http://localhost:8910/. Start from the workspace with `python -B scripts/run_dashboard.py`. Optional `--port` changes the listener. Run it in a terminal to retain the server process. This reads existing users and research records. Session settings use invite signup, observe configuration and no execution credentials; .env is not rewritten. No standalone trading bot is started.

## Observed results

- Public direct probes to Binance, Coinbase, Kraken, CoinGecko and the FX provider all returned HTTP 200 with JSON.
- Final dashboard /health returned healthy. Eight tickers had fresh live prices; BTCUSDT, ETHUSDT and SOLUSDT were verified across three sources.
- /api/market/listings returned 85 assets without an error. Binance, Coinbase, Kraken and CoinGecko all reported connected after successful metadata fetching.
- /api/market/candles for ETHUSDT returned 100 candles without an error. USD/INR returned available.
- /api/laya/status returned OLLAMA_EXPLAIN_ONLY using the installed gemma4-quant:12b. This is model availability for explanations, not evidence that the unfinished trading classifier is active or inference meets its deadline. No generation benchmark was rerun.
- /api/governor/status returned kill_switch_engaged=true. The five-gate governor source is unchanged versus 2024350.
- Browser verification on the initial working port 8901 rendered the terminal and live feed labels with zero JavaScript page errors. The unauthenticated /api/auth/me request returned the expected 401. Subsequent frontend edits passed `node --check cryptoscope/dashboard/static/app.js`.
- The corrected final server runs on 8910. Automatic navigation of the user's existing browser was unavailable because browser control is disabled in Work settings. The old isolated preview still answered on 8900; this report does not claim it was removed.

## Fixes

- Added scripts/run_dashboard.py for a repeatable workspace launch with public data enabled and order settings excluded from its process environment.
- Added real CoinGecko connection status based on actual source, successful fetch time and cache expiry. A Binance fallback does not falsely mark CoinGecko connected. Status API, readiness, SSE and dashboard overview now use this status.
- Reused the initialized AI evaluator in the request handler, removing duplicate initialization and inconsistent startup availability.
- Removed several fixed performance, latency, order-size, memory and clock figures from the main terminal. Missing measurements display unavailable values; this is not a complete audit of all other screens.
- Closed historical candles are no longer overwritten by live tick prices. The chart reloads exchange candles when the next interval closes.

## Validation

`python -B scripts/run_isolated_tests.py cryptoscope/tests/test_market_data.py cryptoscope/tests/test_server_endpoints.py cryptoscope/tests/test_live_terminal_e2e.py cryptoscope/tests/test_secret_leak_prevention.py cryptoscope/tests/test_dashboard_startup.py`

66 collected; 65 passed, 1 skipped in 23.05 seconds; exit 0. Retained test copy: C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-_gwy8tcp. The skipped CoinGecko network test remained disabled inside the isolated suite; public probes and API requests above are separate real online observations. Tests cover metadata provenance/expiry, authentication and emergency recovery boundaries, and process-setting exclusion without parent-environment changes.

## Remaining scope

This restores online dashboard functionality. Phase 1 history/deployment issues, Phase 2 model deadline failures, unfinished Laya classifier integration, and the known exchange-close/reconciliation and protective-stop defects remain unresolved. No full project PASS is claimed. No operational order, history rewrite, dependency installation, account reset, production environment-file edit or cloud deployment was performed. Normal dashboard auth-store initialization and public candle-cache writes are permitted by this launch; earlier verification-only claims of untouched databases do not apply to this normal app run. No database or file was deleted. No Phase 3 or later project phase was executed.
