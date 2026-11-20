# ZILLERS — Change Record

Every modification, upgrade, fix and deletion, newest first, with date and time (IST, UTC+05:30).
Generated from git history by `python scripts/update_changes.py`; regenerate after each commit.
Deleted code remains recoverable from git with `git show <hash>^:<path>`.

Totals: Upgrade 102 · Fix 38 · Modification 13 · Deletion 19 · Docs 27 · Security 2 · Test 3

Types: **Upgrade** = new feature or capability · **Fix** = bug fix · **Modification** = change/refactor/chore · **Deletion** = code or files removed · **Docs** · **Security** · **Test**.

## 2026-11-20 (Friday)

- **07:38 IST** · **Upgrade** · feat(lab): indicator catalog, 11 new candidate strategies, CPCV/PBO/DSR promotion gate (`77cc381`, Ekanth B S)
  - Files: +6 added · ~9 modified · −0 deleted
  - Added: `core/quant/validation.py`, `cryptoscope/desk/indicator_catalog.py`, `tests/test_indicator_catalog.py`, `tests/test_quant_validation.py`, `tests/test_scanner_factors.py`, `tests/test_strategy_lab_gate.py`
  - Details: cryptoscope/desk/indicator_catalog.py: pandas-ta-classic catalog as no-lookahead features (truncation test proves earlier values never change). Strategy Lab: vol-scaled time-series momentum, Donchian/turtle, Bollinger and VWAP reversion, Keltner squeeze, Supertrend, Ichimoku and other catalog rules; long-only, our bracket, net of fees. core/quant/validation.py: triple-barrier labels, CPCV with purge/embargo, PBO (Bailey et al.), reusing the Deflated Sharpe Ratio. Known-answer tests: noise -> PBO ~0.5, planted edge -> low PBO. Promotion gate: >= 100 OOS trades, DSR p < 0.05, PBO < 0.3, positive
- **07:36 IST** · **Docs** · docs: update CHANGES.md (`2919971`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **07:36 IST** · **Upgrade** · feat(models): real THX-02 + Laya as a veto-only meta-label filter; VPIN/regime risk sizing (`317212a`, Ekanth B S)
  - Files: +7 added · ~16 modified · −0 deleted
  - Added: `cryptoscope/agents/decision_models.py`, `cryptoscope/models_sidecar/server.py`, `cryptoscope/quant/flow_risk.py`, `requirements-models.txt`, `scripts/download_decision_models.py`, `tests/test_flow_risk.py`, `tests/test_meta_label_filter.py`
  - Details: Sidecar (cryptoscope/models_sidecar/server.py): HAL-X-AI/THX-02 and convaiinnovations/laya (typed-decisions) behind a token-protected 127.0.0.1:8950 endpoint. Runs in WSL on Windows because Application Control blocks PyTorch's DLLs; the dashboard never imports torch. DebateBot asks both models "target before stop?" alongside the LLM debate; answers go to DebateResult.meta and the new meta_labels journal table. RiskBot vetoes (META_LABEL_SKIP) only when ZILLERS_META_ENFORCE=1; default is shadow mode. Any error = no opinion (fail open). P&L page: take-vs-skip comparison per model with a recommen
- **07:12 IST** · **Docs** · docs: update CHANGES.md (`e07d454`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **07:12 IST** · **Fix** · fix(scanner): measure depth within 0.2% of mid instead of the single best level (`3a1396a`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
  - Details: The best bid/ask level alone flagged BNB ($68) and SUI ($16) as thin although they hold $527k and $186k within 0.2%. Depth now sums the order book (limit 100) within +/-0.2% of mid on the thinner side; minimum $5,000 (ZILLERS_MIN_DEPTH_USD). Unknown depth keeps the coin.
- **07:08 IST** · **Docs** · docs: update CHANGES.md (`d787882`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **07:08 IST** · **Upgrade** · feat(risk): spread/depth filter, daily new-position cap, P&L split by scanner tier (`5ec7b3c`, Ekanth B S)
  - Files: +1 added · ~9 modified · −0 deleted
  - Added: `tests/test_daily_trade_cap.py`
  - Details: Scanner drops pairs with spread > 0.15% (wide_spread) or < $1,000 at the top of book (thin_book); tunable with ZILLERS_MAX_SPREAD / ZILLERS_MIN_TOP_DEPTH_USD; a book outage does not stop the scan. RiskBot caps new positions per UTC day (default 12, ZILLERS_MAX_TRADES_PER_DAY); persisted across restarts. Autopilot logs each coin's tier to work/runtime/scanner_tiers.jsonl; P&L page shows win rate vs break-even and P&L per tier.
- **07:02 IST** · **Docs** · docs: update CHANGES.md (`e250e1f`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **07:02 IST** · **Upgrade** · feat(llm): switch local LLM to qwen3:8b; add risk-off market filter and break-even win-rate stats (`6c21bb2`, Ekanth B S)
  - Files: +1 added · ~13 modified · −0 deleted
  - Added: `tests/test_trade_quality_stats.py`
  - Details: Replaced the five ~8 GB laya/gemma4 chat models with qwen3:8b (~10 tok/s on CPU vs ~1). Scanner skips the weak fallback tiers when the median coin is down 3%+ in 24h. P&L page shows break-even win rate and per-trade Sharpe.

## 2026-11-19 (Thursday)

- **22:17 IST** · **Docs** · docs: update CHANGES.md (`756d16a`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **22:17 IST** · **Upgrade** · feat(autotrade): always pick the best tradeable coins and target 0.5-1% per trade (`c2d2b6c`, Ekanth B S)
  - Files: +0 added · ~6 modified · −0 deleted
  - Details: Scanner: when too few coins pass the daily uptrend filter, fill the 10 slots with SHORT_TERM: 1h uptrend (close > EMA20 > EMA50, RSI1h 40-72) POTENTIAL: best remaining short-term movers, ranked by 0.35 z(r4h/ATR) + 0.25 z(r24h) + 0.25 z(log volume) + 0.15 z(1h volume surge) Both need 0.25%-3% hourly movement and skip free-falls (24h <= -8% or 4h <= -3%). Daily-trend picks still come first; ZILLERS_SCANNER_FALLBACK=0 restores strict mode. Live scan: 10 picks (1 short-term, 9 potential); 5 coins too volatile, several falling fast. StrategyBot SCALP profile (default, ZILLERS_TRADE_PROFILE=SWING f
- **21:39 IST** · **Upgrade** · docs: CHANGES.md dated record of every modification, upgrade, fix and deletion (`38962fc`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `CHANGES.md`, `scripts/update_changes.py`
  - Details: Generated from git history by scripts/update_changes.py (174 commits, 27 Oct - 19 Nov 2026, times in IST); each entry lists type and the files added, modified and deleted.
- **21:39 IST** · **Deletion** · chore(cleanup): delete old strategies, unused bots and one-off research code (`4966f74`, Ekanth B S)
  - Files: +0 added · ~10 modified · −55 deleted
  - Deleted: `core/quant/microstructure/__init__.py`, `core/quant/microstructure/market_making.py`, `core/quant/microstructure/order_flow.py`, `core/quant/microstructure/protections.py`, `cryptoscope/agents/graph.py`, `cryptoscope/agents/researchers/debate.py`, `cryptoscope/autotrader/__main__.py`, `cryptoscope/autotrader/engine.py`, `cryptoscope/autotrader/notifier.py`, `cryptoscope/autotrader/risk.py`, `cryptoscope/autotrader/settings.py`, `cryptoscope/autotrader/signals.py` … and 43 more
  - Details: Import-graph audit from the dashboard and fleet entry points (plus kept tools) found 36 unreachable modules (~4,800 lines). Deleted: old single-process autotrader (engine, signals, risk, store, notifier, settings, __main__) and scripts/start-autotrader.ps1; dashboard /api/autotrader routes that read its files VolatilityBreakoutBot and StatArbStrategyBot (never started by the fleet) duplicate core/quant/microstructure (order_flow, market_making, protections copy) one-off research: research/eval library evaluations, research CLI, agents.graph, research_store, soak/throughput/benchmark tools, ops
- **21:23 IST** · **Fix** · fix(debate): never use a debate model that Ollama does not have installed (`34ea584`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
  - Details: .env sets OLLAMA_MODEL=gemma4:12b, which is not installed here, so the fleet debate (and the START ALL check) got HTTP 404 in 0.2 s and failed closed. resolve_debate_model now checks the configured model against /api/tags and falls back to an installed one of the same base name (gemma4:12b -> gemma4-quant:12b), then any installed quant chat model, logging a warning. If Ollama is unreachable the configured name is kept and the call still fails closed.
- **21:15 IST** · **Upgrade** · feat(system): START ALL button that self-tests every model and launches the bots (`8446176`, Ekanth B S)
  - Files: +3 added · ~3 modified · −0 deleted
  - Added: `cryptoscope/desk/startup.py`, `cryptoscope/execution/testnet_check.py`, `tests/test_startup_all.py`
  - Details: System page: one button (PAPER or TESTNET) that runs, in a background job with a live checklist: safety: kill switch, risk governor, OCaml shadow gate (via WSL), C++/Python kernels data: Binance candles, market scanner, and in TESTNET a signed account check run in a child process (keys never enter the dashboard) decision models: rule PM, SMC + Laya, committee + THX-02, strategy library, HMM, Strategy Lab LLMs: Ollama, a JSON test on every installed chat model, one full fleet debate launch: paper bots, autopilot -> fleet (switches PAPER<->TESTNET only with no open positions) Reports 'All N mode
- **21:02 IST** · **Modification** · chore: keep shell scripts LF so they run inside WSL (`2e2a97c`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `.gitattributes`
- **21:02 IST** · **Upgrade** · feat(ocaml): build and run the OCaml shadow risk gate through WSL on Windows (`46469b0`, Ekanth B S)
  - Files: +1 added · ~4 modified · −0 deleted
  - Added: `ocaml/risk_gate/build_wsl.sh`
  - Details: Windows Code Integrity blocks the native OCaml/mingw toolchain (event 3077), so the gate is compiled with ocamlopt inside WSL (ocaml/risk_gate/build_wsl.sh) and shadow_gate runs a Linux ELF binary via 'wsl.exe --exec' (ZILLERS_WSL_DISTRO). Gate input is now sent as bytes; Windows text mode turned \n into \r\n and broke the last numeric field. main.ml also strips a trailing \r. All three OCaml-vs-Python differential tests now run locally and match.
- **20:47 IST** · **Fix** · fix(debate): let the LLM debate finish so the fleet can approve trades (`6019541`, Ekanth B S)
  - Files: +1 added · ~4 modified · −0 deleted
  - Added: `tests/test_debate_deadline.py`
  - Details: Every one of 266 fleet debates failed closed ('Inference unavailable/timed out'): the model transport capped calls at 35 s while CPU Gemma 12B needs ~60-100 s (~1 token/s). Measured: a debate now returns APPROVE, conviction 8, in ~100 s. deadline_http: max deadline 35 s -> 300 s (worker still killed at the deadline) consensus: use the caller's deadline; shorter JSON fields (max 8 words) fleet: DEBATE_TIMEOUT_SEC 90 -> 180 debate_bot: one debate at a time; a second arriving while busy is rejected as DEBATE_BUSY instead of queueing into a timeout
- **20:36 IST** · **Upgrade** · feat(pnl): P&L dashboard for fleet realised/unrealised, paper bots and decision funnel (`98f40fc`, Ekanth B S)
  - Files: +4 added · ~7 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/pnl.html`, `cryptoscope/dashboard/static/pnl.js`, `cryptoscope/desk/pnl.py`, `tests/test_pnl_dashboard.py`
  - Details: New /pnl page and /api/pnl: net P&L, fleet equity curve, daily P&L, trade stats (win rate, profit factor, expectancy, max drawdown), open positions marked to live price, P&L by coin and exit reason, paper-bot P&L, decision funnel and top risk vetoes. Read-only over the existing journal and execution databases. INR/USD and IST/UTC toggles.
- **10:56 IST** · **Upgrade** · feat(autotrade): exclude BTC/ETH/SOL; rank every liquid coin and trade the top 10 (`3ea2438`, Ekanth B S)
  - Files: +2 added · ~8 modified · −0 deleted
  - Added: `cryptoscope/trading_universe.py`, `tests/test_trading_universe.py`
  - Details: cryptoscope/trading_universe.py: one exclusion list (default BTCUSDT, ETHUSDT, SOLUSDT, override with ZILLERS_EXCLUDE_SYMBOLS) enforced by the scanner, FleetManager and the orchestrator CLI. Scanner shortlist 60 -> 250 and top_n 5 -> 10 (fleet maximum). Fleet start with no symbols uses the scanner's top picks; no BTC/ETH/SOL defaults remain.
- **10:32 IST** · **Fix** · fix(ui): show every model-score chip in the header; unpin header on small screens (`34ec90f`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **10:30 IST** · **Fix** · fix(ui): responsive layout scaling on phone, tablet and wide screens (`eb2590e`, Ekanth B S)
  - Files: +0 added · ~7 modified · −0 deleted
  - Details: The header, heatmap and tables forced pages 430-920px wide on a 375px phone, so browsers zoomed the whole UI out. Header now wraps with a scrolling nav, tables scroll inside their panels, and wide screens keep a one-line header.
- **10:25 IST** · **Upgrade** · feat(ui): ZILLERS logo, wordmark and chrome-on-black brand theme (`6e9b908`, Ekanth B S)
  - Files: +0 added · ~9 modified · −0 deleted
- **10:21 IST** · **Upgrade** · feat(ui): new Aurora visual theme; replace old desk stylesheet (`5a0bc13`, Ekanth B S)
  - Files: +1 added · ~6 modified · −0 deleted
  - Added: `.claude/launch.json`
- **10:16 IST** · **Docs** · docs: algorithms, strategies, formulas and decision architecture reference (`33318db`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `docs/ALGORITHMS_AND_DECISION_ARCHITECTURE.md`

## 2026-11-18 (Wednesday)

- **00:37 IST** · **Upgrade** · feat: Strategy Lab (13 classic strategies) and market-structure data (`53276e8`, Ekanth B S)
  - Files: +5 added · ~8 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/lab.html`, `cryptoscope/dashboard/static/lab.js`, `cryptoscope/desk/market_structure.py`, `cryptoscope/desk/strategy_lab.py`, `tests/test_strategy_lab_and_structure.py`
  - Details: Strategy Lab (/lab): EMA cross, MACD + trend filter, Donchian/Turtle, Bollinger reversion, RSI-2 (Connors), Supertrend, Keltner breakout, Ichimoku, time-series momentum, Williams volatility breakout, Heikin-Ashi, Parabolic SAR, golden cross — all long-only, decided on bar close, filled at next open, same fee Metrics: return, CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, trades, win rate, profit factor, exposure, in-sample vs out-of-sample, permutation p-value (Bonferroni across 13 strategies), vs buy & hold; equity curves on one chart; any symbol and interval Market structure (desk 

## 2026-11-17 (Tuesday)

- **23:51 IST** · **Upgrade** · feat: protections, AI decision journal, rule significance test, grid/DCA paper bots (`a15313e`, Ekanth B S)
  - Files: +6 added · ~11 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/bots.html`, `cryptoscope/dashboard/static/bots.js`, `cryptoscope/desk/ai_journal.py`, `cryptoscope/desk/paperbots.py`, `cryptoscope/execution/protections.py`, `tests/test_repo_inspired_features.py`
  - Details: Ideas adapted from similar open-source projects (independent implementations; no code copied from GPL projects): Protections (freqtrade): persistent per-pair and global locks — cooldown after exit, stop-loss guard, low-profit pairs, closed-trade drawdown — checked by RiskBot before every entry; new locks raise a Telegram alert; System page shows active locks AI decision journal (TradingAgents memory / QuantDinger signal-only accounts): every AI system and every local LLM decision is recorded per bar and scored 5 bars later against real candles (hit rate, average edge); AI SCOREBOARD panel on t
- **23:12 IST** · **Upgrade** · feat(markets): page listing every coin on Binance spot (`2fbca17`, Ekanth B S)
  - Files: +4 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/markets.html`, `cryptoscope/dashboard/static/markets.js`, `cryptoscope/desk/markets.py`, `tests/test_markets_directory.py`
  - Details: /markets: all 519 coins across 1,373 trading pairs and every quote currency (USDT, TRY, USDC, EUR, BTC, ...), grouped by coin Price, 24h change and 24h volume in USD (each quote converted at its own Binance rate) or INR; names, rank, market cap and logos from CoinGecko where available Search, quote filter, gainers/losers/USDT views, sortable columns, expand a coin to see all its pairs, OPEN loads it in the desk (desk now accepts ?symbol=) MARKETS link in every page's navigation; tests for grouping, conversion and stale fallback
- **22:05 IST** · **Upgrade** · feat(scanner): scan all Binance USDT pairs, trade the top 5; fix fleet debate and signal spam (`43ea887`, Ekanth B S)
  - Files: +4 added · ~10 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/scanner.html`, `cryptoscope/dashboard/static/scanner.js`, `cryptoscope/desk/scanner.py`, `tests/test_scanner_autopilot.py`
  - Details: Fixes from the live session log Debate called model gemma4:12b, which is not installed: every call was HTTP 404 and every trade was vetoed. Model now resolves OLLAMA_DEBATE_MODEL > OLLAMA_MODEL > installed gemma model; host without scheme normalised; fleet debate timeout 90 s for CPU Ollama Strategy bot proposed spot SELL (short) trades every 5 s from a stale candle: spot SELL entries are dropped and an identical proposal is not repeated within 15 min Data bot read only the SQLite cache (stale, same price for minutes): it now refreshes closed 15m klines and a 1m live price via CandleStore ever
- **21:45 IST** · **Upgrade** · feat(telegram): notify on every bot trade, close, halt and fleet start/stop (`0ac3912`, Ekanth B S)
  - Files: +2 added · ~7 modified · −0 deleted
  - Added: `cryptoscope/telegram/notify.py`, `tests/test_telegram_trades.py`
  - Details: Fill messages ("BOT TRADE"): price, quantity, value in USD and INR (live USD/INR), stop/target and strategy of the intent the fill belongs to (matched by client order id, not just symbol), debate verdict, mode (PAPER/TESTNET) and IST timestamp Close messages with realised PnL (USD + INR), hold time; halt alerts; all dynamic text HTML-escaped so Telegram never rejects a message Fleet announces itself when online; the dashboard sends a notice when it stops the fleet (including via the master kill switch) One-shot sender (cryptoscope.telegram.notify) run as a child process, so the dashboard never
- **19:41 IST** · **Upgrade** · feat(desk): master kill switch stops trading, fleet and every AI model (`18764b6`, Ekanth B S)
  - Files: +2 added · ~8 modified · −0 deleted
  - Added: `tests/conftest.py`, `tests/test_master_kill.py`
  - Details: One KILL SWITCH button on the desk and System pages (sign-in required; HALT or HALT_FLATTEN): latches the durable emergency halt, stops the autotrader fleet, drops queued LLM jobs and unloads loaded Ollama models, and stops the AI layer The durable latch gates all AI work: desk AI layer, cached AI results and the LLM worker refuse to run while halted, including after a restart Governor status reports ai_layer and fleet_running; fleet start refused while halted System page RESUME dialog (admin password, local only) using the existing resume API Root tests/ now isolate governor state (conftest) 
- **19:27 IST** · **Upgrade** · feat(desk): IST/UTC and INR/USD toggles; strategy library and local LLM panel in the AI layer (`9686919`, Ekanth B S)
  - Files: +1 added · ~7 modified · −0 deleted
  - Added: `cryptoscope/desk/llm_panel.py`
  - Details: Time zone toggle (IST UTC+05:30 default, or UTC) for the chart, transcript, tables and footer Currency toggle: INR = USDT price x live USD/INR from /api/fx/rate (open.er-api); INR is disabled, never estimated, when the rate is unavailable AI layer now also runs the autotrader strategy library (volume breakout, shrink pullback, box oscillation, volatility-compression breakout) on the same closed bars Local LLM panel: every installed Ollama chat model answers BUY/HOLD/SELL as strict JSON from facts computed on real candles, in a background worker, cached per model and bar; the panel majority can
- **18:55 IST** · **Upgrade** · feat(desk): chart time intervals 1m-1w (`1b7bdbf`, Ekanth B S)
  - Files: +0 added · ~8 modified · −0 deleted
  - Details: Interval buttons (1M 5M 15M 30M 1H 4H 1D 1W) on the price chart, remembered per browser The whole desk follows the chosen interval: candles, model votes, PM, paper book, scoreboard and AI layer; volatility and Sharpe annualised per interval Intraday time labels on the chart, transcript and tables; faster polling and shorter server cache on short intervals; unknown intervals rejected with 400 Panel headers wrap on narrow screens
- **18:08 IST** · **Upgrade** · feat(desk): all Binance pairs, AI systems layer, system monitor, autotrader control (`2c2c0ad`, Ekanth B S)
  - Files: +6 added · ~7 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/system.html`, `cryptoscope/dashboard/static/system.js`, `cryptoscope/desk/ai_layer.py`, `cryptoscope/desk/fleet.py`, `cryptoscope/desk/system_monitor.py`, `tests/test_desk_platform.py`
  - Details: Hide the chart library logo (text attribution kept in the footer) Symbol search over every TRADING Binance spot USDT pair (hourly cache, stale fallback) AI layer on the last closed bar: SMC + Laya (FastDecisionLayer) and the hedge-fund committee with THX-02, fed real candles and the desk's own risk numbers; veto-only (can turn a rule BUY into HOLD, never opens or enlarges a position); Ollama status /system page: CPU/cores, RAM, disk, battery, network I/O, server process, HTTPS round-trip to Binance/testnet/Coinbase/Kraken/CoinGecko/Ollama with history, clock offset vs Binance, live feed messag
- **17:55 IST** · **Upgrade + Deletion** · feat(ui): replace the old terminal with the Action Desk (`ccb4607`, Ekanth B S)
  - Files: +7 added · ~4 modified · −3 deleted
  - Deleted: `cryptoscope/dashboard/static/app.js`, `cryptoscope/dashboard/static/index.html`, `cryptoscope/dashboard/static/style.css`
  - Added: `cryptoscope/dashboard/static/desk.css`, `cryptoscope/dashboard/static/desk.html`, `cryptoscope/dashboard/static/desk.js`, `cryptoscope/desk/__init__.py`, `cryptoscope/desk/engine.py`, `cryptoscope/desk/feed.py`, `tests/test_desk_engine.py`
  - Details: New cryptoscope/desk engine: four rule models (trend, momentum, volume, drawdown) vote on real Binance daily candles, a PM aggregates to BUY/HOLD/SELL, a long-only paper book fills at the next open with a per-side fee, models are scored against the next 5 sessions; the forming bar is shown but never decided on /api/desk endpoint (30s cache, input validation, 503 when the feed is down; no cached or synthetic fallback) New desk.html/desk.css/desk.js: price + volume/RSI/MACD charts with paper fills, agent mesh and PM decision, 90-session vote heatmap, equity vs buy & hold, transcript terminal, po
- **00:40 IST** · **Modification** · chore: fix invalid escape sequence in phase 9 report template (`8edc131`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **00:40 IST** · **Modification** · chore: fix invalid escape sequence in phase 9 report template; drop dead variable (`f1709d0`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted

## 2026-11-16 (Monday)

- **17:11 IST** · **Modification** · chore: remove demo workspace, demo CLI/flags and synthetic data from production code (`de32cfb`, Ekanth B S)
  - Files: +0 added · ~11 modified · −0 deleted · 1 renamed
  - Details: Move synthetic demo fixtures to cryptoscope/tests/demo_fixtures.py (test-only) Remove research demo command, backtesting/risk_tools --demo, dashboard demo workspace Dashboard ignores synthetic_demo-sourced artifacts Parquet-dependent evaluation tests skip when no downloaded klines exist
- **16:54 IST** · **Fix** · fix(execution): book offline stop fills, auto-repair protection, persist risk breakers (`a02b230`, Ekanth B S)
  - Files: +2 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/tests/test_protection_repair.py`, `cryptoscope/tests/test_risk_state_persistence.py`
  - Details: Reconcile now books a stop that FILLED while offline (cumulative close accounting, PositionClosed published) instead of only halting Missing/cancelled/expired stops are repaired automatically: adopt an existing owned stop, place a fresh STOP_LOSS, or close at market if price is already through the stop; limited to 3 attempts / 10 min; the durable halt latch is never cleared automatically RiskBot persists NAV/peak/breakers (TESTNET/LIVE), rolls daily figures at UTC midnight, fails closed on unreadable state Software-mode PnL is net of the same 0.1% fee used for entry accounting Tests for stop-f
- **16:34 IST** · **Fix** · fix(execution): harden exchange client and halt handling before testnet soak (`e11ca2c`, Ekanth B S)
  - Files: +1 added · ~4 modified · −0 deleted
  - Added: `cryptoscope/tests/test_exchange_resilience.py`
  - Details: Safety-critical calls (cancel, SELL/stop orders, order status, fills) may probe through a rate-limit cooldown (one per 5s); entries stay blocked Detect -1021 clock skew and retry once after resync; cache server-time offset (no extra /time request per signed call; resync failure no longer fails the call) Retry GET transport errors (2x); never auto-retry order-changing requests; map timeouts/OSError to BinanceNetworkError CRITICAL SystemAlert on every durable halt (60s per-reason dedup) Run periodic exchange reconciliation off the asyncio event loop Health details expose halted state, cooldown a
- **16:19 IST** · **Test** · test: poll instead of fixed sleep in supervisor heartbeat watchdog test (CI flake) (`d2e7168`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **16:18 IST** · **Upgrade** · feat: C++ HMM kernels and OCaml shadow risk gate (`8939f65`, Ekanth B S)
  - Files: +6 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/execution/shadow_gate.py`, `ocaml/risk_gate/bin/dune`, `ocaml/risk_gate/bin/gate.ml`, `ocaml/risk_gate/bin/main.ml`, `ocaml/risk_gate/dune-project`, `tests/test_shadow_risk_gate.py`
  - Details: native: Gaussian HMM EM loop and Viterbi kernels (ABI v2) with Python fallback ocaml/risk_gate: typed re-implementation of RiskGovernor.check_pre_trade (shadow only) cryptoscope/execution/shadow_gate.py: bridge comparing OCaml vs Python verdicts tests: HMM and shadow-gate differential tests; CI job builds OCaml and runs them
- **16:07 IST** · **Upgrade** · feat(native): optional C++ kernels for Monte Carlo drawdown and Hurst exponent (`e61326a`, Ekanth B S)
  - Files: +4 added · ~5 modified · −0 deleted
  - Added: `core/quant/native.py`, `native/build.py`, `native/src/zillers_native.cpp`, `tests/test_native_kernels.py`
  - Details: native/src/zillers_native.cpp: plain C ABI, loaded via ctypes (no Python ABI coupling) Monte Carlo uses a CPython-compatible MT19937 so shuffles are bit-identical core/quant/native.py loader; automatic pure-Python fallback (ZILLERS_NO_NATIVE=1 to force) native/build.py (MSVC/g++/clang++); CI builds it; Dockerfile builds it in builder stage tests/test_native_kernels.py differential tests (skip when library unavailable)
- **15:59 IST** · **Upgrade** · perf(quant): incremental QuantPipeline.on_bar (~107x faster over 2000 bars) (`6cb79ce`, Ekanth B S)
  - Files: +2 added · ~1 modified · −0 deleted
  - Added: `scripts/bench_quant_core.py`, `tests/test_quant_pipeline_incremental.py`
  - Details: Keep running state instead of recomputing full history each bar Keep original as ReferenceQuantPipeline oracle; add differential tests Add scripts/bench_quant_core.py baseline benchmark Validate prices before mutating state
- **15:43 IST** · **Upgrade** · ci: skip data/network-dependent tests on CI, add fastparquet, upgrade setuptools, install Chromium (`c9d4a64`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **15:37 IST** · **Modification** · ci: drop quantstats from CI deps (needs numpy<2) and skip its test when absent (`2971a4a`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **15:34 IST** · **Modification** · ci: make requirements installable on Python 3.11 and add test-suite deps (`02fbe05`, Ekanth B S)
  - Files: +1 added · ~2 modified · −0 deleted
  - Added: `requirements-ci.txt`
  - Details: numpy/scipy pins gated by python_version (latest pins need 3.12+) add requirements-ci.txt (joblib, sklearn, lightgbm, pandas, pyarrow, ...)
- **15:19 IST** · **Test** · test: skip parquet-dependent tests when no parquet engine is usable (`5dbe438`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **15:12 IST** · **Modification** · chore: fix Docker/CI coverage, add LICENSE, correct docs (`b6a1fe7`, Ekanth B S)
  - Files: +1 added · ~5 modified · −0 deleted
  - Added: `LICENSE`
  - Details: Dockerfile: copy core/ so dashboard core.* imports work pytest.ini: include root tests/ in testpaths CI: run on feat/quant-engine-terminal, install requirements, lint core/ Add MIT LICENSE README: correct dependency, test-count and INVITE_CODE claims STATUS: remove duplicated Phase 6/7 sections and stale branch line

## 2026-11-12 (Thursday)

- **09:10 IST** · **Docs** · docs(visuals): capture and embed updated production screenshots showing IST chart, live feeds, and workstation (`cbf8784`, Ekanth B S)
  - Files: +2 added · ~5 modified · −0 deleted
  - Added: `docs/images/02-tradingview-chart-ist.png`, `docs/images/06-mobile-responsive-terminal.png`
- **09:04 IST** · **Fix** · fix(market-feed, chart): ensure persistent streaming, polling fallback, and exact IST scale alignment (`6f3c8ab`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **08:48 IST** · **Fix** · fix(chart): align TradingView chart time scale and crosshair to Indian Standard Time (IST) (`69183db`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **08:39 IST** · **Upgrade** · feat(timing): configure Indian Standard Time (IST UTC+05:30) trading sessions and clock across terminal (`94a6e06`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **08:27 IST** · **Fix** · fix(ui, auth): enhance sign-in visibility and responsive layout scaling across all viewports (`f640b1d`, Ekanth B S)
  - Files: +0 added · ~6 modified · −0 deleted

## 2026-11-11 (Wednesday)

- **20:14 IST** · **Upgrade** · feat(quant-workstation): wire 10-level quant telemetry, live Alpha158 committee & THX-02 deep reasoning cards (`25c1306`, Ekanth B S)
  - Files: +0 added · ~4 modified · −0 deleted
- **19:31 IST** · **Upgrade** · feat(chart): support 1m default interval with 1s, 30s, 1m, 2m, and 5m selectable views (`e2c60ad`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted
- **19:18 IST** · **Upgrade** · feat(feed): implement real-time WebSocket market data streaming with sub-30ms latency tracking and UI telemetry (`5eab08f`, Ekanth B S)
  - Files: +0 added · ~9 modified · −0 deleted
- **18:38 IST** · **Upgrade** · feat(agents): implement THX-02 Thinking Decision Engine, wire into HedgeFundCommittee, and expose dashboard API (`e0b10b1`, Ekanth B S)
  - Files: +2 added · ~4 modified · −0 deleted
  - Added: `core/agents/thx02_decision_engine.py`, `tests/test_thx02_decision_engine.py`
- **17:56 IST** · **Upgrade** · feat(ui): add 10-level quant matrix and hedge fund deliberation workstation views (`af3c3e8`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **17:52 IST** · **Upgrade** · feat(dashboard): expose 10-level quant telemetry and multi-agent committee endpoints (`b6eecaf`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **08:02 IST** · **Upgrade** · feat(quant): implement Levels 8, 9, 10 formulas and unit tests (`712ba12`, Ekanth B S)
  - Files: +7 added · ~0 modified · −0 deleted
  - Added: `core/quant/levels/__init__.py`, `core/quant/levels/level10_research.py`, `core/quant/levels/level8_risk.py`, `core/quant/levels/level9_microstructure.py`, `tests/test_level10_research.py`, `tests/test_level8_risk.py`, `tests/test_level9_microstructure.py`
- **08:02 IST** · **Upgrade** · feat(quant): implement microstructure, protections, alpha158 factors, and multi-agent deliberation committee (`320675e`, Ekanth B S)
  - Files: +13 added · ~0 modified · −0 deleted
  - Added: `core/agents/__init__.py`, `core/agents/hedge_fund_committee.py`, `core/quant/factors/__init__.py`, `core/quant/factors/alpha158.py`, `core/quant/microstructure/__init__.py`, `core/quant/microstructure/market_making.py`, `core/quant/microstructure/order_flow.py`, `core/quant/microstructure/protections.py` … and 5 more
- **08:01 IST** · **Upgrade** · feat(quant): implement Levels 5, 6, 7 (Time Series, Stochastics, Derivatives) with 31 unit tests (`17f9270`, Ekanth B S)
  - Files: +7 added · ~0 modified · −0 deleted
  - Added: `core/quant/levels/__init__.py`, `core/quant/levels/level5_timeseries.py`, `core/quant/levels/level6_stoch.py`, `core/quant/levels/level7_derivatives.py`, `tests/test_level5_timeseries.py`, `tests/test_level6_stoch.py`, `tests/test_level7_derivatives.py`
- **08:00 IST** · **Upgrade** · feat(quant): implement Levels 1-4 math core with 20 formulas and TDD unit tests (`fef3cba`, Ekanth B S)
  - Files: +9 added · ~0 modified · −0 deleted
  - Added: `core/quant/levels/__init__.py`, `core/quant/levels/level1_prob.py`, `core/quant/levels/level2_stats.py`, `core/quant/levels/level3_linalg.py`, `core/quant/levels/level4_opt.py`, `tests/test_level1_prob.py`, `tests/test_level2_stats.py`, `tests/test_level3_linalg.py` … and 1 more
- **07:51 IST** · **Docs** · docs: add 10-level quant theory and multi-agent system specification and plan (`c9470f9`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `docs/superpowers/plans/2026-11-11-quant-theory-10-levels-and-multi-agent-system.md`, `docs/superpowers/specs/2026-11-11-quant-theory-10-levels-and-multi-agent-system.md`

## 2026-11-10 (Tuesday)

- **21:44 IST** · **Fix** · fix(quant): address code review findings for microprice, equity tracking, and rate limiting (`328c5e3`, Ekanth B S)
  - Files: +0 added · ~6 modified · −0 deleted
- **21:20 IST** · **Upgrade** · feat(dashboard): add Bloomberg/Fincept multi-pane views and quant telemetry API (`b4c8f92`, Ekanth B S)
  - Files: +1 added · ~3 modified · −0 deleted
  - Added: `tests/test_terminal_dashboard_api.py`
- **21:12 IST** · **Upgrade** · feat(quant): implement AI Berkshire qualitative research committee (`02cd827`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/berkshire_committee.py`, `tests/test_berkshire_committee.py`
- **21:11 IST** · **Upgrade** · feat(quant): integrate 8-stage quant pipeline and multi-asset portfolio coordinator (`5e17fb6`, Ekanth B S)
  - Files: +3 added · ~0 modified · −0 deleted
  - Added: `core/quant/__init__.py`, `core/quant/pipeline.py`, `tests/test_quant_pipeline.py`
- **21:09 IST** · **Upgrade** · feat(quant): implement stage 8 validation and Monte Carlo engine (formulas 8.1-8.6) (`e3e0123`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage8_validate.py`, `tests/test_stage8_validate.py`
- **21:08 IST** · **Upgrade** · feat(quant): implement stage 7 risk and kill-switch engine (formulas 7.1-7.6) (`8bb246a`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage7_risk.py`, `tests/test_stage7_risk.py`
- **21:07 IST** · **Upgrade** · feat(quant): implement stage 6 execution analysis engine (formulas 6.1-6.6) (`bb622ed`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage6_execute.py`, `tests/test_stage6_execute.py`
- **21:06 IST** · **Upgrade** · feat(quant): implement stage 5 position sizing engine (formulas 5.1-5.6) (`3493128`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage5_size.py`, `tests/test_stage5_size.py`
- **21:05 IST** · **Upgrade** · feat(quant): implement stage 4 edge evaluation engine (formulas 4.1-4.6) (`3a47b5b`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage4_edge.py`, `tests/test_stage4_edge.py`
- **21:03 IST** · **Upgrade** · feat(quant): implement stage 3 filter engine (formulas 3.1-3.6) (`9f3ab52`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage3_filter.py`, `tests/test_stage3_filter.py`
- **21:02 IST** · **Upgrade** · feat(quant): implement stage 2 signal engine (formulas 2.1-2.6) (`2872882`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage2_signal.py`, `tests/test_stage2_signal.py`
- **21:01 IST** · **Upgrade** · feat(quant): implement stage 1 data cleaning engine (formulas 1.1-1.6) (`ae9d7a3`, Ekanth B S)
  - Files: +2 added · ~0 modified · −0 deleted
  - Added: `core/quant/stage1_data.py`, `tests/test_stage1_data.py`
- **20:59 IST** · **Modification** · chore: add .superpowers/ to .gitignore (`46e8969`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **20:55 IST** · **Docs** · docs: add implementation plan for 8-stage quant engine and terminal (`fedbcb5`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `docs/superpowers/plans/2026-11-10-quant-pipeline-and-terminal.md`
- **20:52 IST** · **Docs** · docs: add design spec for 8-stage 48-formula quant engine and terminal (`936747e`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `docs/superpowers/specs/2026-11-09-quant-pipeline-and-terminal-design.md`

## 2026-11-09 (Monday)

- **23:39 IST** · **Docs** · docs: record branch consolidation across main, verified-fleet, repo-eval, multi-coin, and laya-decision (`0440847`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **21:14 IST** · **Upgrade** · feat(phase-9): complete sandbox evaluation of quantitative tools and compile master report (`650b57e`, Ekanth B S)
  - Files: +16 added · ~7 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/assets/LIGHTWEIGHT_CHARTS_LICENSE.txt`, `cryptoscope/dashboard/static/assets/lightweight-charts.standalone.production.js`, `cryptoscope/research/eval/__init__.py`, `cryptoscope/research/eval/apscheduler_eval.py`, `cryptoscope/research/eval/drex_eval.py`, `cryptoscope/research/eval/duckdb_eval.py`, `cryptoscope/research/eval/quantstats_eval.py`, `cryptoscope/research/eval/reviews.py` … and 8 more
- **20:14 IST** · **Upgrade** · feat(phase-8): complete Laya Tier 2 decision integration, baseline evaluation, serving latency benchmarks, and side-by-side backtest (`c440ff1`, Ekanth B S)
  - Files: +9 added · ~3 modified · −0 deleted
  - Added: `cryptoscope/research/laya/label_generator.py`, `cryptoscope/research/laya/models.py`, `cryptoscope/research/laya/probe.py`, `cryptoscope/research/laya/serving.py`, `cryptoscope/research/laya/train_evaluate.py`, `cryptoscope/tests/test_phase8_laya.py`, `reports/PHASE_8_LAYA_EVALUATION.json`, `reports/PHASE_8_REPORT.md` … and 1 more
- **19:30 IST** · **Upgrade** · feat(phase-6-7): complete 4-year multi-coin backtest, drift monitoring, runbook, and accountant ledger (`2645263`, Ekanth B S)
  - Files: +13 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/research/multi_coin/drift_monitor.py`, `cryptoscope/research/multi_coin/strategy_engine.py`, `cryptoscope/research/multi_coin/trade_ledger.py`, `cryptoscope/tests/test_phase6_research.py`, `cryptoscope/tests/test_phase7_operations.py`, `docs/RUNBOOK.md`, `reports/ACCOUNTANT_TRADE_LEDGER.csv`, `reports/PHASE_6_BACKTEST_RESULTS.json` … and 5 more
- **19:12 IST** · **Upgrade** · feat(phase-5): implement point-in-time universe, dynamic cost model, and portfolio risk gating (`72d06c0`, Ekanth B S)
  - Files: +7 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/research/multi_coin/cost_model.py`, `cryptoscope/research/multi_coin/portfolio_risk.py`, `cryptoscope/research/multi_coin/universe_manager.py`, `cryptoscope/tests/test_phase5_universe_and_risk.py`, `reports/PHASE_5_REPORT.md`, `reports/PHASE_5_UNIVERSE_AND_RISK.json`, `scripts/run_phase5_universe_and_risk.py`
- **19:02 IST** · **Upgrade** · feat(phase-4): ingest 4-year 1h klines and verify multi-coin data integrity (`e68bd36`, Ekanth B S)
  - Files: +9 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/research/multi_coin/__init__.py`, `cryptoscope/research/multi_coin/candidate_universe.py`, `cryptoscope/research/multi_coin/data_integrity.py`, `cryptoscope/research/multi_coin/kline_downloader.py`, `cryptoscope/tests/test_phase4_data.py`, `data/universe/candidate_spot_usdt.json`, `reports/PHASE_4_DATA_INTEGRITY.json`, `reports/PHASE_4_REPORT.md` … and 1 more
- **18:40 IST** · **Upgrade** · feat(phase-3): complete Phase 3 exchange verification and launch 7-day testnet run (`708a1fd`, Ekanth B S)
  - Files: +1 added · ~5 modified · −0 deleted
  - Added: `scripts/run_testnet_7day_run.py`
- **18:00 IST** · **Docs** · docs(phase-3): record final tests and localhost readiness (`f275629`, Ekanth B S)
  - Files: +1 added · ~2 modified · −0 deleted
  - Added: `reports/PHASE_3_REPAIR_TEST_OUTPUT_FINAL.txt`
- **17:57 IST** · **Docs** · docs(phase-3): hand over bounded testnet and operations evidence (`df6ddb6`, Ekanth B S)
  - Files: +7 added · ~2 modified · −0 deleted
  - Added: `reports/PHASE_3_REPAIR_BENCHMARK.csv`, `reports/PHASE_3_REPAIR_BENCHMARK.json`, `reports/PHASE_3_REPAIR_EXCHANGE_RESULT.json`, `reports/PHASE_3_REPAIR_SOAK.csv`, `reports/PHASE_3_REPAIR_SOAK.json`, `reports/PHASE_3_REPAIR_SOAK_PROTOCOL.json`, `reports/PHASE_3_REPAIR_TEST_OUTPUT.txt`
- **17:56 IST** · **Fix** · fix(phase-3): reconcile testnet fills stops and owned orders (`ec60df1`, Ekanth B S)
  - Files: +6 added · ~8 modified · −0 deleted
  - Added: `cryptoscope/execution/accounting.py`, `cryptoscope/execution/lifecycle.py`, `cryptoscope/execution/phase3_checks.py`, `cryptoscope/tests/exchange_fixtures.py`, `cryptoscope/tests/test_phase3_followup.py`, `scripts/run_phase3_testnet_checks.py`
- **17:55 IST** · **Fix** · fix(phase-3): bound model calls and verify operations readiness (`b1d0525`, Ekanth B S)
  - Files: +2 added · ~9 modified · −0 deleted
  - Added: `cryptoscope/ops/soak_analysis.py`, `cryptoscope/providers/deadline_http.py`

## 2026-11-07 (Saturday)

- **14:49 IST** · **Docs** · docs(phase-3): record verified operations and remaining exchange blockers (`5f7f6c1`, Ekanth B S)
  - Files: +22 added · ~1 modified · −0 deleted
  - Added: `reports/PHASE_3_AUTH.json`, `reports/PHASE_3_BACKUP_FINAL.json`, `reports/PHASE_3_BACKUP_INITIAL.json`, `reports/PHASE_3_BACKUP_SCHEDULE.json`, `reports/PHASE_3_BACKUP_SCHEDULED.json`, `reports/PHASE_3_BENCHMARK.csv`, `reports/PHASE_3_BENCHMARK.json`, `reports/PHASE_3_DATABASES_AFTER.json` … and 14 more
- **14:44 IST** · **Fix** · fix(backups): fail verification when no database was captured (`5bb2144`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **14:32 IST** · **Docs** · docs(safety): align activation spec with executable governor (`c939ed0`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **14:24 IST** · **Test** · test(operations): benchmark real compact debate responses twice (`c0359f8`, Ekanth B S)
  - Files: +2 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/ops/debate_benchmark.py`, `scripts/run_phase3_benchmark.py`
- **14:24 IST** · **Fix** · fix(markets): derive listings from verified active Spot pairs (`daaf237`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **14:24 IST** · **Fix** · fix(execution): retain uncertain exposure and verify exchange exits (`bdd20ed`, Ekanth B S)
  - Files: +1 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/tests/test_phase3_operations.py`
- **14:24 IST** · **Fix** · fix(operations): standardize SQLite and measure isolated dashboard load (`e0b899c`, Ekanth B S)
  - Files: +6 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/ops/__init__.py`, `cryptoscope/ops/databases.py`, `cryptoscope/ops/telemetry.py`, `cryptoscope/storage/sqlite.py`, `scripts/run_database_backups.py`, `scripts/run_phase3_soak.py`

## 2026-11-06 (Friday)

- **17:06 IST** · **Fix** · fix(live-data): replace stale preview and expire outdated quotes (`2de2349`, Ekanth B S)
  - Files: +2 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/tests/test_live_feed.cjs`, `reports/LIVE_DATA_REPAIR.md`
- **12:15 IST** · **Docs** · docs(phase-2): verify completed cache replay and integrity gate (`7a18c83`, Ekanth B S)
  - Files: +2 added · ~2 modified · −0 deleted
  - Added: `reports/PHASE_2_REPAIR_RESULTS.json`, `reports/PHASE_2_REPAIR_TEST_OUTPUT.txt`
- **12:10 IST** · **Fix** · fix(risk): latch drawdown breaches across recovery (`364f72e`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **12:04 IST** · **Fix** · fix(phase-2): complete recorded debate and tighten backtest integrity (`1cdcda0`, Ekanth B S)
  - Files: +2 added · ~10 modified · −0 deleted
  - Added: `cryptoscope/backtesting/compact_debate.py`, `cryptoscope/tests/test_phase2_repairs.py`
- **11:50 IST** · **Fix** · fix(dashboard): connect online data and correct runtime status (`b8ea76b`, Ekanth B S)
  - Files: +3 added · ~6 modified · −0 deleted
  - Added: `cryptoscope/tests/test_dashboard_startup.py`, `reports/LOCAL_DASHBOARD_ONLINE_REPORT.md`, `scripts/run_dashboard.py`

## 2026-11-05 (Thursday)

- **07:22 IST** · **Docs** · docs(phase-2): record local-model attempts and fail-closed replay (`2024350`, Ekanth B S)
  - Files: +2 added · ~2 modified · −0 deleted
  - Added: `reports/PHASE_2_ONLINE_EVIDENCE.json`, `reports/PHASE_2_ONLINE_TEST_OUTPUT.txt`
- **07:20 IST** · **Upgrade** · feat(research): add guarded local-model debate cache generation (`4720f62`, Ekanth B S)
  - Files: +3 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/backtesting/local_model_cache.py`, `cryptoscope/tests/test_local_model_cache.py`, `scripts/run_phase2_online.py`
- **06:51 IST** · **Docs** · docs(phase-2): record offline integrity evidence and blocked gate (`f5b455c`, Ekanth B S)
  - Files: +4 added · ~1 modified · −0 deleted
  - Added: `reports/PHASE_2_PAIR_VIOLATIONS.csv`, `reports/PHASE_2_REPORT.md`, `reports/PHASE_2_RESULTS.json`, `reports/PHASE_2_TEST_OUTPUT.txt`
- **06:48 IST** · **Fix** · fix(backtest): replay real risk offline and audit pair losses (`f7a704d`, Ekanth B S)
  - Files: +9 added · ~4 modified · −0 deleted
  - Added: `cryptoscope/backtesting/debate_cache.py`, `cryptoscope/backtesting/fleet_replay.py`, `cryptoscope/backtesting/integrity.py`, `cryptoscope/backtesting/legacy_audit.py`, `cryptoscope/backtesting/pair_audit.py`, `cryptoscope/backtesting/risk_exercises.py`, `cryptoscope/backtesting/stationarity.py`, `cryptoscope/tests/test_phase2_backtest_integrity.py` … and 1 more
- **01:51 IST** · **Docs** · docs(phase-1): record verified security work and unresolved gate (`676af22`, Ekanth B S)
  - Files: +3 added · ~5 modified · −0 deleted
  - Added: `reports/PHASE_1_COLLABORATION_AUDIT.json`, `reports/PHASE_1_HISTORY_SCAN.json`, `reports/PHASE_1_REPORT.md`
- **01:47 IST** · **Fix** · fix(security): preserve structured redaction and stored data boundaries (`eca6ebd`, Ekanth B S)
  - Files: +2 added · ~8 modified · −0 deleted
  - Added: `scripts/scan_git_history_secrets.py`, `scripts/scan_report_secrets.py`
- **00:56 IST** · **Fix** · fix(config): handle blank optional testnet endpoint safely (`dfb007f`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **00:53 IST** · **Fix** · fix(forms): validate submissions and sign operator sessions (`98fdc5c`, Ekanth B S)
  - Files: +3 added · ~3 modified · −0 deleted
  - Added: `landing/lib/server/form-security.ts`, `landing/tests/form-security.test.mjs`, `supabase/migrations/20261104_restrict_collaboration_reads.sql`
- **00:53 IST** · **Fix** · fix(security): persist emergency halt and harden local boundaries (`9d04251`, Ekanth B S)
  - Files: +7 added · ~18 modified · −0 deleted
  - Added: `cryptoscope/security/__init__.py`, `cryptoscope/security/config.py`, `cryptoscope/security/halt_state.py`, `cryptoscope/security/public_forms.py`, `cryptoscope/security/report_secrets.py`, `cryptoscope/tests/conftest.py`, `cryptoscope/tests/test_phase1_security.py`

## 2026-11-04 (Wednesday)

- **21:03 IST** · **Docs** · docs(phase-0): record approved branch and isolated baseline (`0887fa7`, Ekanth B S)
  - Files: +4 added · ~0 modified · −0 deleted
  - Added: `docs/MASTER_PROMPT.md`, `docs/STATUS.md`, `reports/PHASE_0_REPORT.md`, `scripts/run_isolated_tests.py`
- **18:14 IST** · **Modification** · Update README.md (`26c4408`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **18:10 IST** · **Modification** · chore(research): create requirements-research.txt for heavy ML dependencies per Absolute Rule 8 (`75d915e`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `requirements-research.txt`
- **18:07 IST** · **Fix** · fix(execution): adapt watchdog grace period to scale with supervisor timeout (`e23ee1a`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **18:04 IST** · **Security** · security(A8): redact all secret fragments from reports and add automated leak prevention test (`4ab9a65`, Ekanth B S)
  - Files: +1 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/tests/test_secret_leak_prevention.py`
- **08:02 IST** · **Upgrade** · feat(backtest): add fees paid, stage veto counters, and combined portfolio metrics to fleet backtest (`f8437b6`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **08:00 IST** · **Upgrade** · feat(execution): add watchdog grace period to prevent premature trade churn during supervisor glitches (`7852a45`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **07:56 IST** · **Fix** · fix(telegram): add owner_user_id constructor parameter and hermetic test fixture (`8181a07`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **07:46 IST** · **Security** · security(A1): remove Telegram /resume from kill-switch path; check both chat_id and user_id (`6226406`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
  - Details: After /kill, Telegram cannot lift the halt under any circumstances (no args, 'confirm', correct password, arbitrary string — all BLOCKED) Remove password-based resumption entirely from cmd_resume kill-switch branch Remove /resume <admin_password> hint from cmd_kill response message Remove /resume from cmd_start help listing Update confirm_resume callback to not hint at password-based recovery is_authorized() now checks BOTH effective_chat.id AND effective_user.id when TELEGRAM_OWNER_USER_ID is configured (prevents group-member impersonation) 11 tests: test_kill_cannot_be_resumed_via_telegram_e

## 2026-11-03 (Tuesday)

- **22:31 IST** · **Upgrade + Deletion** · feat(orchestrator): add CLI entrypoint and sync updated landing assets to dashboard static (`3a6e008`, Ekanth B S)
  - Files: +2 added · ~0 modified · −1 deleted · 1 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-mkXJAAx2.css`
  - Added: `cryptoscope/dashboard/static/assets/index-89HR0zbe.css`, `cryptoscope/orchestrator/__main__.py`
- **21:32 IST** · **Upgrade** · feat(orchestrator): implement Binance Spot Testnet execution with exchange stop-loss and isolation tests (`85403d4`, Ekanth B S)
  - Files: +2 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/execution/binance_testnet.py`, `cryptoscope/tests/test_binance_testnet.py`
- **20:56 IST** · **Upgrade + Deletion** · feat(ui): add Indian and Karnataka flag emojis to about section (`ccfe303`, Ekanth B S)
  - Files: +2 added · ~3 modified · −1 deleted · 1 renamed
  - Deleted: `cryptoscope/dashboard/static/landing/assets/index-mkXJAAx2.css`
  - Added: `cryptoscope/dashboard/static/landing/assets/index-89HR0zbe.css`, `landing/src/components/FlagEmoji.tsx`
  - Details: Create FlagEmoji component with high-fidelity Karnataka and India SVG flag emojis Include specular emoji depth, rounded clip corners, and dark-theme metallic borders Add Karnataka and India flag badges to About section header, author dossier, and footer Update mobile layout with responsive flag badges Rebuild production bundle and sync with dashboard static landing assets
- **20:08 IST** · **Upgrade** · feat(orchestrator): production hardening and fleet verification (`10298c5`, Ekanth B S)
  - Files: +9 added · ~13 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/stat_arb_bot.py`, `cryptoscope/orchestrator/bots/volatility_breakout_bot.py`, `cryptoscope/research/benchmark_debate_models.py`, `cryptoscope/research/inspect_databases.py`, `cryptoscope/research/measure_throughput.py`, `cryptoscope/research/run_fleet_backtest.py`, `cryptoscope/research/run_soak_test.py`, `cryptoscope/tests/test_graceful_shutdown.py` … and 1 more
  - Details: Benchmark Ollama debate candidates; select gemma4:12b (91.7% valid JSON, p50 22.59s, budget 35s) Redesign consensus debate to single combined call with strict fail-closed fallback Overhaul position sizing to Fixed Fractional Risk (0.5% default) and gate Kelly behind flag + 300 trades Implement VolatilityBreakoutBot and StatArbStrategyBot; run 90-day walk-forward backtest Enforce AST broker import isolation exclusively to ExecutionBot Add password-protected /kill emergency stop and verify live Telegram alerts Benchmark HTTP throughput (119 req/s) and verify graceful shutdown with WAL checkpoint
- **18:30 IST** · **Fix** · fix(market): ensure live candle freshness and strictly filter unlisted/unpriced tokens (`8033ce6`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted

## 2026-11-02 (Monday)

- **23:03 IST** · **Upgrade** · feat(config): auto-load credentials.env into environment at startup (`b6dbb1a`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **20:46 IST** · **Modification** · chore(security): add credentials.env and *.env patterns to .gitignore (`9ad24f7`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **19:50 IST** · **Docs** · docs: add comprehensive Multi-Bot and Telegram Gateway production verification report (`ca826af`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `MULTI_BOT_PRODUCTION_REPORT.md`
- **19:48 IST** · **Upgrade** · feat(orchestrator): add OrchestratorEngine, e2e real candle replay, and comprehensive failure injection suite (`24360cd`, Ekanth B S)
  - Files: +2 added · ~6 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/engine.py`, `cryptoscope/tests/test_multi_bot_e2e.py`
- **19:38 IST** · **Upgrade** · feat(telegram): add TelegramGateway with owner whitelist, safety invariants, and interactive commands (`ba3209e`, Ekanth B S)
  - Files: +3 added · ~0 modified · −0 deleted
  - Added: `cryptoscope/telegram/__init__.py`, `cryptoscope/telegram/gateway.py`, `cryptoscope/tests/test_telegram_gateway.py`
- **19:36 IST** · **Upgrade** · feat(orchestrator): add JournalBot and NotifierBot with rate limiting and offline spooling (`5fab8cf`, Ekanth B S)
  - Files: +3 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/journal_bot.py`, `cryptoscope/orchestrator/bots/notifier_bot.py`, `cryptoscope/tests/test_journal_and_notifier.py`
- **19:32 IST** · **Upgrade** · feat(orchestrator): add ExecutionBot with stop-loss orders and AST isolation test (`69eb133`, Ekanth B S)
  - Files: +3 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/execution_bot.py`, `cryptoscope/tests/test_exchange_isolation.py`, `cryptoscope/tests/test_orchestrator_execution.py`
- **19:27 IST** · **Upgrade** · feat(orchestrator): add deterministic RiskBot with hard safety limits (`22d4034`, Ekanth B S)
  - Files: +2 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/risk_bot.py`, `cryptoscope/tests/test_orchestrator_risk.py`
- **19:26 IST** · **Upgrade** · feat(orchestrator): add Data, Analyst, Quant, Strategy, and Debate bots (`48b60c3`, Ekanth B S)
  - Files: +6 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/analyst_bot.py`, `cryptoscope/orchestrator/bots/data_bot.py`, `cryptoscope/orchestrator/bots/debate_bot.py`, `cryptoscope/orchestrator/bots/quant_bot.py`, `cryptoscope/orchestrator/bots/strategy_bot.py`, `cryptoscope/tests/test_pipeline_bots.py`
- **19:24 IST** · **Upgrade** · feat(orchestrator): add BaseBot interface and SupervisorBot with crash recovery (`0dad83b`, Ekanth B S)
  - Files: +3 added · ~0 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/bots/__init__.py`, `cryptoscope/orchestrator/bots/supervisor_bot.py`, `cryptoscope/tests/test_orchestrator_supervisor.py`
- **19:22 IST** · **Upgrade** · feat(orchestrator): add typed events and asynchronous event bus (`e789d56`, Ekanth B S)
  - Files: +6 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/orchestrator/__init__.py`, `cryptoscope/orchestrator/base_bot.py`, `cryptoscope/orchestrator/event_bus.py`, `cryptoscope/orchestrator/events.py`, `cryptoscope/tests/test_orchestrator_bus.py`, `docs/superpowers/plans/2026-11-02-multi-bot-orchestrator.md`
- **19:00 IST** · **Upgrade** · feat(prod-hardening): complete production hardening, 10-suite real-data verification, and audit report (`00c00cd`, Ekanth B S)
  - Files: +6 added · ~13 modified · −0 deleted
  - Added: `Caddyfile`, `PRODUCTION_REPORT.md`, `deploy/cloudflare-tunnel.yml`, `requirements.txt`, `start.bat`, `start.sh`
- **17:47 IST** · **Docs** · docs: add Phase 0 security and architecture baseline audit (AUDIT.md) (`5f0737d`, Ekanth B S)
  - Files: +1 added · ~0 modified · −0 deleted
  - Added: `AUDIT.md`
- **17:36 IST** · **Docs** · docs: add comprehensive quantitative architecture, system dataflow, and mathematical trading formulas manual (`3429e2d`, Ekanth B S)
  - Files: +1 added · ~1 modified · −0 deleted
  - Added: `ZILLERS_QUANT_ARCHITECTURE.md`
- **17:21 IST** · **Upgrade** · feat(quant): integrate statistical arbitrage, OU mean-reversion, Parkinson/GK volatility, CVD order flow, and Kelly sizing (`4b70659`, Ekanth B S)
  - Files: +8 added · ~6 modified · −0 deleted
  - Added: `cryptoscope/autotrader/strategies/stat_arb_pairs.py`, `cryptoscope/autotrader/strategies/volatility_breakout.py`, `cryptoscope/quant/__init__.py`, `cryptoscope/quant/order_flow.py`, `cryptoscope/quant/sizing.py`, `cryptoscope/quant/stat_arb.py`, `cryptoscope/quant/volatility.py`, `cryptoscope/tests/test_quant_analysis.py`
- **16:49 IST** · **Fix** · fix(market): filter listings to active Binance spot pairs and resolve ticker prices (`0943739`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **16:30 IST** · **Upgrade** · feat(terminal): complete frontend-backend integration, purge demo data, add live e2e tests (`41d5916`, Ekanth B S)
  - Files: +1 added · ~3 modified · −0 deleted
  - Added: `cryptoscope/tests/test_live_terminal_e2e.py`
- **16:02 IST** · **Upgrade** · feat(risk): integrate QuantOrb on-chain holder scanner, operator clustering, and AMM sell-impact guard into 5-gate governor (`daa091e`, Ekanth B S)
  - Files: +3 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/risk_tools/amm_impact.py`, `cryptoscope/risk_tools/onchain_guard.py`, `cryptoscope/tests/test_onchain_guard.py`
- **15:52 IST** · **Upgrade** · feat(quant): integrate TradingAgents adversarial debate, daily_stock_analysis breakout strategies, and day-trader-skill Monte Carlo odds engine (`a624c89`, Ekanth B S)
  - Files: +14 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/agents/consensus.py`, `cryptoscope/agents/researchers/bear_researcher.py`, `cryptoscope/agents/researchers/bull_researcher.py`, `cryptoscope/agents/risk/tri_debate.py`, `cryptoscope/autotrader/notifier.py`, `cryptoscope/autotrader/strategies/__init__.py`, `cryptoscope/autotrader/strategies/box_oscillation.py`, `cryptoscope/autotrader/strategies/shrink_pullback.py` … and 6 more
- **06:23 IST** · **Upgrade + Deletion** · feat(security): hide operator proposals desk from public view on all devices and keep dedicated portal route (`24d4e77`, Ekanth B S)
  - Files: +2 added · ~6 modified · −2 deleted · 2 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-CQ-9sEsI.css`, `cryptoscope/dashboard/static/landing/assets/index-CQ-9sEsI.css`
  - Added: `cryptoscope/dashboard/static/assets/index-mkXJAAx2.css`, `cryptoscope/dashboard/static/landing/assets/index-mkXJAAx2.css`

## 2026-11-01 (Sunday)

- **23:55 IST** · **Fix + Deletion** · fix(ui): remove all discovery links, switcher buttons, and machine-readable tags from visible UI (`faf3a16`, Ekanth B S)
  - Files: +2 added · ~4 modified · −2 deleted · 2 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-CYhPPi1e.css`, `cryptoscope/dashboard/static/landing/assets/index-CYhPPi1e.css`
  - Added: `cryptoscope/dashboard/static/assets/index-CQ-9sEsI.css`, `cryptoscope/dashboard/static/landing/assets/index-CQ-9sEsI.css`
- **23:39 IST** · **Fix + Deletion** · fix(security): hide and wipe passcode from UI/API messages and remove discovery links from footer (`fb4596d`, Ekanth B S)
  - Files: +2 added · ~9 modified · −2 deleted · 2 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-BJX8h4Sq.css`, `cryptoscope/dashboard/static/landing/assets/index-BJX8h4Sq.css`
  - Added: `cryptoscope/dashboard/static/assets/index-CYhPPi1e.css`, `cryptoscope/dashboard/static/landing/assets/index-CYhPPi1e.css`
- **22:45 IST** · **Upgrade + Deletion** · feat(seo-geo-aeo): configure full SEO, Generative Engine Optimization (llms.txt), Answer Engine Optimization (FAQ Schema.org), robots.txt, and sitemap.xml (`e5b21ed`, Ekanth B S)
  - Files: +18 added · ~7 modified · −2 deleted · 2 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-D73zAvpn.css`, `cryptoscope/dashboard/static/landing/assets/index-D73zAvpn.css`
  - Added: `cryptoscope/dashboard/static/assets/index-BJX8h4Sq.css`, `cryptoscope/dashboard/static/landing/assets/index-BJX8h4Sq.css`, `cryptoscope/dashboard/static/landing/llms-full.txt`, `cryptoscope/dashboard/static/landing/llms.txt`, `cryptoscope/dashboard/static/landing/manifest.json`, `cryptoscope/dashboard/static/landing/robots.txt`, `cryptoscope/dashboard/static/landing/sitemap.xml`, `cryptoscope/dashboard/static/llms-full.txt` … and 10 more
- **22:16 IST** · **Upgrade + Deletion** · feat(mobile): build lightweight mobile phone version with reduced pictography and desktop recommendation callout (`0f17cff`, Ekanth B S)
  - Files: +5 added · ~2 modified · −4 deleted
  - Deleted: `cryptoscope/dashboard/static/assets/index-BpVtnTHC.css`, `cryptoscope/dashboard/static/assets/index-e-4atVdG.js`, `cryptoscope/dashboard/static/landing/assets/index-BpVtnTHC.css`, `cryptoscope/dashboard/static/landing/assets/index-e-4atVdG.js`
  - Added: `cryptoscope/dashboard/static/assets/index-D73zAvpn.css`, `cryptoscope/dashboard/static/assets/index-DSFU9Zt6.js`, `cryptoscope/dashboard/static/landing/assets/index-D73zAvpn.css`, `cryptoscope/dashboard/static/landing/assets/index-DSFU9Zt6.js`, `landing/src/components/MobileHome.tsx`
- **22:01 IST** · **Upgrade** · feat(redirect): redirect vercel.app traffic to https://zillers.zienorganisation.online/collaborate (`057bef6`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted · 2 renamed
- **21:42 IST** · **Upgrade** · feat(deploy): add Vercel serverless functions, Supabase schema, and passcode protection with Ekanthbs@4514 (`41bdda3`, Ekanth B S)
  - Files: +5 added · ~6 modified · −0 deleted
  - Added: `landing/api/auth.ts`, `landing/api/collaborate.ts`, `landing/api/collaborations.ts`, `landing/vercel.json`, `supabase/migrations/20261101_init_collaborations.sql`
- **21:12 IST** · **Upgrade** · feat(repo): add platform visuals, collaborate submissions desk, and remove underlines under Zien Organisation (`88c9804`, Ekanth B S)
  - Files: +10 added · ~8 modified · −0 deleted · 4 renamed
  - Added: `cryptoscope/dashboard/collaborate_view.py`, `docs/images/01-tactical-trading-terminal.png`, `docs/images/02-orderbook-liquidity-heatmap.png`, `docs/images/03-algorithmic-strategy-engine.jpg`, `docs/images/04-5gate-risk-governor-killswitch.png`, `docs/images/05-automated-bot-fleet.png`, `docs/images/06-sub-ms-performance-telemetry.png`, `docs/images/z-emblem.png` … and 2 more
- **20:56 IST** · **Upgrade + Deletion** · feat(branding): link all Zien Organisation references to https://ziennexus.app/ (`f20ed18`, Ekanth B S)
  - Files: +2 added · ~6 modified · −2 deleted · 2 renamed
  - Deleted: `cryptoscope/dashboard/static/assets/index-ZoP74dUT.css`, `cryptoscope/dashboard/static/landing/assets/index-ZoP74dUT.css`
  - Added: `cryptoscope/dashboard/static/assets/index-BqT2cyk3.css`, `cryptoscope/dashboard/static/landing/assets/index-BqT2cyk3.css`
- **20:45 IST** · **Upgrade + Deletion** · feat(docs): add comprehensive setup guide page, collaboration viewer utility, and align repo README (`07a61c4`, Ekanth B S)
  - Files: +6 added · ~7 modified · −4 deleted
  - Deleted: `cryptoscope/dashboard/static/assets/index-CwvtzW2_.css`, `cryptoscope/dashboard/static/assets/index-DMMDZnN6.js`, `cryptoscope/dashboard/static/landing/assets/index-CwvtzW2_.css`, `cryptoscope/dashboard/static/landing/assets/index-DMMDZnN6.js`
  - Added: `cryptoscope/dashboard/static/assets/index-ZoP74dUT.css`, `cryptoscope/dashboard/static/assets/index-qMtc92wg.js`, `cryptoscope/dashboard/static/landing/assets/index-ZoP74dUT.css`, `cryptoscope/dashboard/static/landing/assets/index-qMtc92wg.js`, `landing/src/components/SetupGuide.tsx`, `scripts/view_collaborations.py`
- **20:37 IST** · **Fix** · fix(attribution): remove underline under Ekanth B S and highlight with bold styling only (`2341502`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted · 4 renamed
- **20:32 IST** · **Upgrade + Deletion** · feat(showcase): make module arrows interactive with modals, add working windows gallery, and fix logo cache-busting (`d665002`, Ekanth B S)
  - Files: +22 added · ~8 modified · −4 deleted
  - Deleted: `cryptoscope/dashboard/static/assets/index-BGG3h-sC.js`, `cryptoscope/dashboard/static/assets/index-DyKLw967.css`, `cryptoscope/dashboard/static/landing/assets/index-BGG3h-sC.js`, `cryptoscope/dashboard/static/landing/assets/index-DyKLw967.css`
  - Added: `cryptoscope/dashboard/static/assets/emblem-a8TWfvVw.png`, `cryptoscope/dashboard/static/assets/index-C0MUKfzh.js`, `cryptoscope/dashboard/static/assets/index-syBpVXE5.css`, `cryptoscope/dashboard/static/assets/zien-emblem-DX3_LMpi.png`, `cryptoscope/dashboard/static/assets/zillers-showcase-logo-88gAaXQf.png`, `cryptoscope/dashboard/static/landing/assets/emblem-a8TWfvVw.png`, `cryptoscope/dashboard/static/landing/assets/index-C0MUKfzh.js`, `cryptoscope/dashboard/static/landing/assets/index-syBpVXE5.css` … and 14 more
- **20:19 IST** · **Upgrade + Deletion** · feat(branding): integrate metallic ZILLERS logo suite and author attribution for Ekanth B S (`98619f3`, Ekanth B S)
  - Files: +22 added · ~15 modified · −4 deleted
  - Deleted: `cryptoscope/dashboard/static/assets/index-Uv_KoObx.js`, `cryptoscope/dashboard/static/assets/index-xaZvPL2K.css`, `cryptoscope/dashboard/static/landing/assets/index-Uv_KoObx.js`, `cryptoscope/dashboard/static/landing/assets/index-xaZvPL2K.css`
  - Added: `cryptoscope/dashboard/static/assets/index-BGG3h-sC.js`, `cryptoscope/dashboard/static/assets/index-DyKLw967.css`, `cryptoscope/dashboard/static/assets/z-app-icon.png`, `cryptoscope/dashboard/static/assets/z-emblem-large.png`, `cryptoscope/dashboard/static/assets/zillers-brand-hero.png`, `cryptoscope/dashboard/static/assets/zillers-horizontal-lockup.png`, `cryptoscope/dashboard/static/assets/zillers-logo-main.png`, `cryptoscope/dashboard/static/assets/zillers-showcase-logo.png` … and 14 more
- **20:18 IST** · **Modification** · Revise README title and project description (`d2cb54f`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
  - Details: Updated project title and description in README.
- **20:12 IST** · **Upgrade + Deletion** · feat(landing): add collaborate and build together page with profile submission (`651a106`, Ekanth B S)
  - Files: +5 added · ~6 modified · −6 deleted
  - Deleted: `cryptoscope/dashboard/static/assets/index-BOKltCXo.css`, `cryptoscope/dashboard/static/assets/index-BgMnV2bQ.js`, `cryptoscope/dashboard/static/assets/index-BqkSt9MV.js`, `cryptoscope/dashboard/static/landing/assets/index-BOKltCXo.css`, `cryptoscope/dashboard/static/landing/assets/index-BgMnV2bQ.js`, `cryptoscope/dashboard/static/landing/assets/index-BqkSt9MV.js`
  - Added: `cryptoscope/dashboard/static/assets/index-Uv_KoObx.js`, `cryptoscope/dashboard/static/assets/index-xaZvPL2K.css`, `cryptoscope/dashboard/static/landing/assets/index-Uv_KoObx.js`, `cryptoscope/dashboard/static/landing/assets/index-xaZvPL2K.css`, `landing/src/components/Collaborate.tsx`
- **20:00 IST** · **Fix** · fix(header): remove version 4.2 monochrome edition badges from headers (`ce197ff`, Ekanth B S)
  - Files: +2 added · ~4 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/assets/index-BqkSt9MV.js`, `cryptoscope/dashboard/static/landing/assets/index-BqkSt9MV.js`
- **19:55 IST** · **Upgrade** · feat(landing): build ZILLERS premium monochrome fintech landing page and showcase (`c273ba2`, Ekanth B S)
  - Files: +36 added · ~4 modified · −0 deleted
  - Added: `cryptoscope/dashboard/static/assets/index-BOKltCXo.css`, `cryptoscope/dashboard/static/assets/index-BgMnV2bQ.js`, `cryptoscope/dashboard/static/landing/assets/emblem.png`, `cryptoscope/dashboard/static/landing/assets/index-BOKltCXo.css`, `cryptoscope/dashboard/static/landing/assets/index-BgMnV2bQ.js`, `cryptoscope/dashboard/static/landing/assets/logo.png`, `cryptoscope/dashboard/static/landing/assets/zien-emblem.png`, `cryptoscope/dashboard/static/landing/assets/zillers-logo.png` … and 28 more
- **19:04 IST** · **Docs** · docs: document Phase 12 GUI overhaul and dark institutional theme (`ab74399`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **19:04 IST** · **Fix** · fix(gui): dark institutional color theme and custom cryptocurrency picker (`425c258`, Ekanth B S)
  - Files: +0 added · ~3 modified · −0 deleted
- **18:43 IST** · **Docs** · docs: update TRANSFORMATION_CHANGES.md with Phase 11 candlestick chart and multi-asset streaming (`1fd775c`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **18:40 IST** · **Upgrade** · feat(ui): implement candlestick bars, multi-asset chart switcher, fix crypto listings, and enable real-time SSE streaming (`21ada0b`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted
- **15:08 IST** · **Fix** · fix(review-pass-2): add scrypt semaphore, gate 3 trade timestamp derivation, testnet withdrawal blocking, and laya selftest (`03c7202`, Ekanth B S)
  - Files: +1 added · ~8 modified · −0 deleted
  - Added: `scripts/laya_selftest.py`
- **14:41 IST** · **Docs** · docs: update TRANSFORMATION_CHANGES.md with review pass, test suite counts, and commit audit (`1cf4279`, Ekanth B S)
  - Files: +0 added · ~1 modified · −0 deleted
- **14:35 IST** · **Fix** · fix(review): complete review pass on auth, governor, kill-switch, execution, laya, freshness, ci, and docs (`fc13926`, Ekanth B S)
  - Files: +2 added · ~18 modified · −0 deleted
  - Added: `TRANSFORMATION_CHANGES.md`, `cryptoscope/auth/cli.py`
- **13:00 IST** · **Upgrade** · feat(prod): finalize production readiness, non-root docker setup, ci matrix, and regulatory disclaimers (`87266ec`, Ekanth B S)
  - Files: +0 added · ~6 modified · −0 deleted
- **12:29 IST** · **Upgrade** · feat(execution): implement 5-gate live trading governor, emergency kill switch, and risk limiters (`c29110f`, Ekanth B S)
  - Files: +2 added · ~2 modified · −0 deleted
  - Added: `cryptoscope/execution/governor.py`, `cryptoscope/tests/test_governor.py`
- **12:20 IST** · **Upgrade** · feat(backtesting): implement realistic crypto cost model, Section 115BBH/194S tax engine, Deflated Sharpe Ratio, and Schedule VDA export (`5685f9c`, Ekanth B S)
  - Files: +2 added · ~1 modified · −0 deleted
  - Added: `cryptoscope/backtesting/cost_model.py`, `cryptoscope/tests/test_backtest_costs.py`
- **12:16 IST** · **Upgrade** · feat(decision): implement Tier 1 sub-20ms rules, Laya Tier 2 async evaluator, latency benchmark, and training dataset exporter (`2789fce`, Ekanth B S)
  - Files: +3 added · ~4 modified · −0 deleted
  - Added: `cryptoscope/autotrader/decision.py`, `scripts/bench_laya.py`, `scripts/export_training_set.py`
- **12:06 IST** · **Upgrade** · feat(screener): implement all-crypto listings table, 30d changes, sorting, volume filter, and quick actions (`b59599c`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted
- **12:01 IST** · **Upgrade** · feat(auth): implement 32-byte salt scrypt, tiered lockout backoff, CSRF enforcement, and reauth (`35d86e0`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted
- **11:54 IST** · **Upgrade** · feat(fx): enforce real public FX service with stale handling and UI toggle visibility (`83a358e`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **11:52 IST** · **Upgrade** · feat(market_data): implement Kraken feed, real-time SSE ticker endpoint, and multi-source concurrency (`324e94d`, Ekanth B S)
  - Files: +1 added · ~5 modified · −0 deleted
  - Added: `cryptoscope/market_data/kraken_feed.py`
- **11:43 IST** · **Upgrade** · feat(market_data): support 1h, 24h, 7d, and 30d rolling windows (`8e98328`, Ekanth B S)
  - Files: +0 added · ~2 modified · −0 deleted
- **11:22 IST** · **Upgrade + Deletion** · feat(prod): complete crypto-only transition, Docker, CI, docs, and test fixtures (`b15df98`, Ekanth B S)
  - Files: +98 added · ~3 modified · −16 deleted
  - Deleted: `Modelfile`, `cryptoscope/__init__.py`, `cryptoscope/tests/__init__.py`, `cryptoscope/tests/test_binance_feed.py`, `cryptoscope/tests/test_decision_engine.py`, `cryptoscope/tests/test_quant_engine.py`, `cryptoscope/tests/test_server_api.py`, `docs/TECHNICAL_ARCHITECTURE.md`, `docs/assets/architecture_diagram.svg`, `docs/assets/flow_preview.svg`, `docs/assets/terminal_hero.jpg`, `docs/assets/terminal_preview.png` … and 4 more
  - Added: `.github/workflows/ci.yml`, `CHANGELOG.md`, `Dockerfile`, `cryptoscope/.gitignore`, `cryptoscope/backtesting/__init__.py`, `cryptoscope/backtesting/__main__.py`, `cryptoscope/backtesting/runner.py`, `cryptoscope/backtesting/validation.py` … and 90 more
- **11:21 IST** · **Upgrade + Deletion** · feat(dashboard): add institutional terminal UI, listings screener, and auth views (`2676343`, Ekanth B S)
  - Files: +12 added · ~0 modified · −7 deleted
  - Deleted: `cryptoscope/server.py`, `cryptoscope/static/crypto-chart.js`, `cryptoscope/static/flow.html`, `cryptoscope/static/flow.js`, `cryptoscope/static/workspace.css`, `cryptoscope/static/workspace.html`, `cryptoscope/static/workspace.js`
  - Added: `cryptoscope/dashboard/__init__.py`, `cryptoscope/dashboard/__main__.py`, `cryptoscope/dashboard/data.py`, `cryptoscope/dashboard/static/app.js`, `cryptoscope/dashboard/static/assets/emblem.png`, `cryptoscope/dashboard/static/assets/logo.png`, `cryptoscope/dashboard/static/assets/zien-emblem.png`, `cryptoscope/dashboard/static/assets/zillers-logo.png` … and 4 more
- **11:21 IST** · **Upgrade + Deletion** · feat(engine): add SMC order block detection, directional scoring, and grounded Laya AI (`c44be49`, Ekanth B S)
  - Files: +53 added · ~0 modified · −1 deleted
  - Deleted: `cryptoscope/laya_ai.py`
  - Added: `config/.gitkeep`, `config/autotrader.json`, `config/features.json`, `config/local-cpu.json`, `config/research.json`, `config/risk-observations.example.json`, `cryptoscope/agents/.gitkeep`, `cryptoscope/agents/__init__.py` … and 45 more
- **11:21 IST** · **Upgrade + Deletion** · feat(auth): implement scrypt hashing, account lockout backoff, and session store (`4286abf`, Ekanth B S)
  - Files: +4 added · ~0 modified · −2 deleted
  - Deleted: `cryptoscope/security.py`, `cryptoscope/session_manager.py`
  - Added: `cryptoscope/auth/__init__.py`, `cryptoscope/auth/security.py`, `cryptoscope/auth/store.py`, `cryptoscope/tests/test_auth.py`
- **11:21 IST** · **Upgrade + Deletion** · feat(market_data): add multi-source crypto aggregator, real FX engine, and kline store (`ec787b2`, Ekanth B S)
  - Files: +11 added · ~0 modified · −7 deleted
  - Deleted: `cryptoscope/binance_feed.py`, `cryptoscope/crypto_archive.py`, `cryptoscope/crypto_market.py`, `cryptoscope/decision_engine.py`, `cryptoscope/manage.py`, `cryptoscope/quant_engine.py`, `server.py`
  - Added: `cryptoscope/fx/__init__.py`, `cryptoscope/fx/rate_service.py`, `cryptoscope/market_data/__init__.py`, `cryptoscope/market_data/aggregator.py`, `cryptoscope/market_data/base.py`, `cryptoscope/market_data/binance_feed.py`, `cryptoscope/market_data/candle_store.py`, `cryptoscope/market_data/coinbase_feed.py` … and 3 more

## 2026-10-28 (Wednesday)

- **18:13 IST** · **Docs** · Docs: Add comprehensive institutional technical architecture specification (`6831730`, Ekanth B S)
  - Files: +1 added · ~1 modified · −0 deleted
  - Added: `docs/TECHNICAL_ARCHITECTURE.md`

## 2026-10-27 (Tuesday)

- **22:59 IST** · **Fix** · Fix: Real-time chat copilot instant responses, chart canvas rendering, and UI score levels (`e0ba12c`, Ekanth B S)
  - Files: +0 added · ~5 modified · −0 deleted
- **22:43 IST** · **Modification** · Initial release: Zien Crypto Institutional Trading Software with SMC Order Blocks, Real-Time CVD, 4-Quadrant Leverage Matrix, and Local Laya AI Copilot (`0f68a2c`, Ekanth B S)
  - Files: +35 added · ~0 modified · −0 deleted
  - Added: `.env.example`, `.gitignore`, `Modelfile`, `README.md`, `cryptoscope/__init__.py`, `cryptoscope/binance_feed.py`, `cryptoscope/crypto_archive.py`, `cryptoscope/crypto_market.py` … and 27 more
