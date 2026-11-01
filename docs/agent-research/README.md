# Zien Laya Research Backend

For the latest CloddsBot, Vibe-Trading, Everything Claude Trading and Kronos additions, see [the four-repository review and commands](FOUR_REPOSITORY_REVIEW.md).

The autonomous spot simulator is documented in [Autonomous Laya paper trader](AUTOTRADER.md). It has its own ledger, a compact one-call Laya decision path and continuous quote-based protective checks.

Python 3.12+ and its standard library are sufficient for the research backend and dashboard. Optional QuantJourney backtesting uses its isolated environment; Clodds risk diagnostics use Node.js. See [repository feature integration](FEATURE_INTEGRATION.md) for commands, installed capabilities and remaining work. Laya runs through Ollama; configure the exact installed model with `OLLAMA_MODEL` or `config/research.json`. There is no automatic substitute model. The original terminal sources were deleted before this work; this backend runs independently of them.

Each demo invocation creates a fresh ledger under `work/research-demo/<session-id>/`. Previous demo sessions and real research accounts are preserved. This makes demonstrations repeatable without carrying an earlier synthetic position into the next run.

Laya role calls use native JSON schemas with required fields, bounded strings, and no additional fields. Every response is also validated locally for that schema. Incomplete/malformed JSON or a schema violation gets one audited regeneration with the same model and a shorter text/list allowance. A second invalid response fails the run. Network failures are not retried. Audit logs retain both attempts, finish reasons, token usage and raw responses.

## Run from the project root

Start the professional, read-only local dashboard:

```powershell
python -m cryptoscope.dashboard --port 8900
```

Open `http://localhost:8900`. Keep the command running while using the dashboard. It refreshes every five seconds, monitors runs started from another terminal, and includes saved close-price charts, decisions, stage progress, paper positions, risk settings, and JSON report downloads. Select **Demo sandbox** to inspect synthetic runs separately. Charts show archived snapshots rather than a live market feed. No orders or inference calls can be started from the dashboard. It uses the Python standard library and serves assets locally without a frontend build step.

Dashboard server and database reader live in `cryptoscope/dashboard/`; HTML, CSS, and JavaScript live in `cryptoscope/dashboard/static/`.

```powershell
# Isolated, synthetic offline example; does not call Laya or Binance.
python -m cryptoscope.research demo
python -m cryptoscope.research demo --paper

# Check the configured model in an already-running Ollama instance.
python -m cryptoscope.research doctor

# Actual Laya research with public Binance data; no order placed.
python -m cryptoscope.research analyze --live --symbol BTCUSDT

# Explicit opt-in to the spot simulator, with fresh bid/ask validation.
python -m cryptoscope.research analyze --live --symbol BTCUSDT --paper

python -m cryptoscope.research status
python -m cryptoscope.research mark --symbol BTCUSDT
python -m cryptoscope.research pause-entries
python -m cryptoscope.research resume-entries
python -m pytest -q
```

`OLLAMA_HOST` defaults to `http://127.0.0.1:11434` and `OLLAMA_MODEL` to `laya-crypto:latest`. To select an existing Laya model in PowerShell:

The installed Laya model supports thinking. Research defaults to thinking disabled, concise reports, 512 output tokens per call and a 120-second per-call timeout for local performance. These limits are configurable. A truncated or invalid response fails the run rather than producing a partial trade.

```powershell
$env:OLLAMA_MODEL = 'your-installed-laya-model:tag'
python -m cryptoscope.research doctor
```

Optional development tools: `python -m pip install -r requirements-dev.txt`. Override settings with `python -m cryptoscope.research --config path/to/overrides.json analyze --live`.

Use the longer `config/local-cpu.json` preset for local inference: `python -m cryptoscope.research --config config/local-cpu.json analyze --live --symbol BTCUSDT`. It allows up to ten minutes per call. After replacing generic JSON output with strict role schemas, a full seven-call run against the installed `laya-crypto:latest` completed successfully (run `bc33752045974ba8be95eb0553b98ad7`, HOLD decision, no order). Earlier attempts failed due to timeouts or incomplete output. If inference outlasts snapshot freshness or decision expiry, execution is still refused.

## Component ownership

| Folder | Responsibility |
| --- | --- |
| `config/research.json` | Model, universe, data freshness and risk settings |
| `cryptoscope/providers/` | Ollama/Laya and public Binance HTTP adapters |
| `cryptoscope/agents/analysts/` | Closed-candle technicals, supplied derivatives and news |
| `cryptoscope/agents/researchers/` | Laya bull/bear debate |
| `cryptoscope/agents/graph.py` | Analysts → debate → trader → three risk reviews → portfolio manager |
| `cryptoscope/agents/schemas.py` | Input and proposal validation |
| `cryptoscope/agents/risk/` | Deterministic sizing and execution checks |
| `cryptoscope/execution/` | Spot paper ledger, fees, slippage, explicit mark exits |
| `cryptoscope/storage/` | SQLite stage audit records |
| `cryptoscope/backtesting/` | QuantJourney verification and archived-candle strategy baselines |
| `cryptoscope/risk_tools/`, `integrations/clodds-risk/` | Validated Python bridge and vendored Clodds risk modules |
| `cryptoscope/dashboard/` | Local monitor, backtest inspector and feature map |
| `cryptoscope/research/` | CLI, configuration, demo, JSON/Markdown reports |
| `cryptoscope/tests/` | Offline contract, risk, accounting and workflow tests |
| `data/raw/`, `data/snapshots/` | Archived vendor payloads and normalized snapshots |
| `reports/research/`, `reports/demo/` | Reports per run, separated by mode |
| `work/research-agent/`, `work/research-demo/` | Separate research and demo SQLite ledgers |

## Behavior and boundaries

Default watchlist is BTCUSDT and ETHUSDT. Current execution supports spot longs, partial reductions and closes, with at most one open position across the portfolio. SHORT proposals are recorded but refused by the simulator. Cash starts at 10,000 USDT; default risk is 0.5% with a 10% notional cap. Reward/risk includes estimated entry/exit fees and slippage. Position size is computed by code, never from model confidence. Execution revalidates the proposal and current account under a SQLite write transaction. Reusing a filled run ID returns its existing fill.

All seven research roles use the same configured Laya model and run sequentially to avoid flooding local hardware; a role can make one additional call to regenerate invalid JSON. The three deterministic analysts run in parallel. Optional `analyze --kronos` adds a validated local forecast as evidence. Missing derivatives/news remain explicitly unavailable. News supplied through an imported snapshot must include `published_at` and `available_at` Unix timestamps. The public feed currently collects spot candles and fresh bid/ask quotes only.

Imported snapshots (`analyze --snapshot file.json`) use the same schema as files under `data/snapshots/`. They must contain at least 50 contiguous closed candles and a current `as_of` timestamp. Historical replay is not implemented yet. Automatic candle fetching never includes the currently open candle. A snapshot may expire while inference runs, in which case execution is rejected. Reports contain model names, settings, prompts, outputs, input data, stage results, and errors.

Stop/target exits run only when the `mark` command is invoked. There is no continuous background execution, exchange order API, futures accounting, liquidation simulation, news collector, on-chain collector, or learned memory. QuantJourney evaluates deterministic historical baselines; historical Laya replay is pending. SQLite records stage checkpoints for inspection; automatic resume is not implemented. The pre-existing `work/runtime` databases are not used by this backend. Paper-entry pause/resume is persistent and allows exits while paused.

API references used for the adapters: [Ollama generation](https://docs.ollama.com/api/generate) and [Binance public market data](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints).
