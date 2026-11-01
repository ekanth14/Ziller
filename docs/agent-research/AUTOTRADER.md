# Autonomous Laya paper trader

The bot buys, holds and sells simulated BTC/USDT and ETH/USDT spot positions using public Binance prices and the configured local `laya-crypto:latest` model. SELL closes coins it already holds; there is no shorting or live exchange order API. The user selected paper trading for this implementation.

## Start and monitor

From the project root:

```powershell
# Run continuously in this terminal.
python -m cryptoscope.autotrader start

# Or launch a hidden background process with timestamped logs.
.\scripts\start-autotrader.ps1

# Monitor the dedicated paper account and latest decisions.
python -m cryptoscope.autotrader status
python -m cryptoscope.dashboard --port 8900
```

Open `http://localhost:8900/#autotrader`. Restart an older dashboard server to load its new API endpoints. The Autonomous paper trader panel shows runtime state, heartbeat, pending inference, separate paper cash/equity, positions, risk halts, decision latency, fills and inspectable reports. Existing research/demo accounts are separate.

```powershell
# One bounded decision; optionally review a HOLD-only context with Laya.
python -m cryptoscope.autotrader once --force-review

# Persistent entry controls; exits still run while the process is active.
python -m cryptoscope.autotrader pause-entries
python -m cryptoscope.autotrader resume-entries

# Gracefully stop the process and discard an in-flight model decision.
python -m cryptoscope.autotrader stop

# After stopping, explicitly reset latched loss/drawdown baselines.
# This uses fresh position marks and preserves the daily entry counter.
python -m cryptoscope.autotrader reset-risk
```

Stopping the process leaves any simulated positions recorded and stops protective monitoring. Restarting resumes monitoring those positions before considering a new decision. The bot does not register itself for Windows startup or automatically restart after an OS reboot.

## Decision loop

1. Poll executable bid/ask quotes and apply protective stops/targets. The target interval is five seconds; network latency can make it longer.
2. Refresh closed five-minute candles. The receiving data cutoff is the earlier of exchange time and local observation time, so a clock offset cannot admit future candles.
3. Compute EMA, RSI, ATR, volume and breakout features locally. No open candles enter these features.
4. Apply entry prefilters, then ask Laya for a two-field typed decision: BUY, SELL or HOLD and an eligible strategy. It cannot set position size or modify risk limits. The audit retains the signal evidence instead of asking for a generated rationale.
5. Validate the response locally, recheck the current portfolio, quote, spread, freshness, deadline and persistent limits, then atomically fill an allowed paper order.

There is at most one active inference call and one decision per symbol/closed candle. Duplicate candle keys survive restarts. Abandoned in-flight decisions are never replayed. An OS file lock prevents two bot processes from owning the same paper account.

The main loop continues fetching quotes and managing protective exits while inference runs in its single worker thread. If a protective fill changes the account during inference, the resulting model action is discarded. New entry controls are checked inside the same SQLite transaction as the fill; pausing entries during inference therefore blocks that entry.

## Compatible algorithms

| Candidate | Entry condition |
| --- | --- |
| EMA trend | EMA20 above EMA50, close at/above EMA20, RSI in [45,70) |
| RSI rebound | RSI below 30 and last close above the preceding close |
| Volume breakout | Last close above the preceding 20-bar high, volume at least 1.2 times the preceding 20-bar average, RSI below 75 |

Laya can reject every candidate and HOLD. When a position exists it can HOLD or SELL. Missing news and derivatives are explicitly unknown. Quiet or risk-blocked flat accounts can HOLD without invoking the model; those records are labeled `deterministic_prefilter`, not Laya output.

The broader multi-role research workflow, Kronos forecasts and historical validation remain available as separate research tools. The bot uses the compatible spot signal definitions above; it does not claim to implement every strategy or skill in the reviewed repositories, or to have established these strategies' profitability.

## Speed and limits

The compact path makes one Laya call instead of a seven-role research cycle. It disables thinking, limits output to 48 tokens, uses the installed model's verified 4096-token context and requests a 15-minute model keep-alive. Shorter 1024/2048 context attempts stalled during local verification; they are not used by the bot. These are supported Ollama controls: [generation API](https://docs.ollama.com/api/generate), [context configuration](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size).

The default socket timeout is 45 seconds; a decision more than 60 seconds old is discarded. Invalid output or a failed call produces no order and is recorded. The fast bot performs no automatic model retries. These bounds limit how long it will accept a decision; actual latency depends on local hardware, prompt evaluation and model loading. A one-shot run also has a 120-second run budget and exits unsuccessfully if no valid decision completed.

Each submitted model call and complete response remain in the decision audit. Latency shown by the dashboard includes the loop's completion-observation delay; model token/timing fields are also available in the inspector.

The existing proposal schema has a confidence field. Fast mode does not request a model confidence score: its unused compatibility value is zero and never controls sizing. The actual model output contains only action and strategy.

Defaults live in `config/autotrader.json`:

| Control | Default |
| --- | --- |
| Account | Separate 10,000 USDT simulated balance |
| Positions | At most one open spot position across both symbols |
| Risk budget | 0.25% of cash per entry; size also capped by allocation/cash |
| Allocation | At most 10% notional |
| Entry cooldown | Five minutes after an entry or exit |
| Daily entries | At most five, counted by UTC day |
| Daily loss halt | 2% of that day's starting net liquidation value |
| Drawdown halt | 5% below the persistent equity high-water mark |
| Spread limit | 0.15% |
| Quote freshness | At most 10 seconds |
| Snapshot freshness | At most 120 seconds since capture |
| Stop distance | Maximum of 2 ATR and 0.5% of expected entry; entries requiring over 5% are refused |
| Target | 2:1 estimated reward/risk after configured fees/slippage |
| Trailing stop | Only tightens, once price clears entry plus the trailing distance |

Daily loss/drawdown halts are latched. Midnight and `resume-entries` do not clear them. Only explicit `reset-risk` reanchors these baselines, with the process stopped. The daily entry counter and recent-trade cooldown remain intact. Stop, target and model exits are permitted while entries are halted.

Net liquidation value includes estimated exit fees/slippage. Fee and slippage assumptions come from `config/research.json`. Circuit limits depend on fresh observed quotes and cannot guarantee an exact maximum loss through a price gap or data outage.

Override supported bot settings with `python -m cryptoscope.autotrader --config config/my-paper-bot.json start`. The config loader refuses live mode, unconfigured symbols and invalid bounds.

## Files

| Location | Responsibility |
| --- | --- |
| `cryptoscope/autotrader/engine.py` | Concurrent inference and protective quote loop |
| `cryptoscope/autotrader/signals.py` | Causal candidates, compact context and deterministic levels |
| `cryptoscope/autotrader/risk.py` | Transactional persistent risk and trailing stops |
| `cryptoscope/autotrader/store.py` | Process lock, heartbeat, decision keys and events |
| `work/autotrader/paper.sqlite3` | Dedicated simulated cash, positions, fills and risk state |
| `work/autotrader/autotrader.sqlite3` | Runtime, stop command, decision audit and events |
| `reports/autotrader/<id>/report.json` | Portable decision artifacts |
| `work/autotrader/engine-*.log` | Background process output/errors |

The runtime uses the existing Python standard library and local Ollama adapter. It requires no new exchange keys, messaging services or Python packages.

## Local latency verification

The reduced two-field prompt completed a real local `laya-crypto:latest` decision in 7.625 seconds on 2026-10-31, returning `HOLD` / `none`. The probe used fresh public Binance data and did not execute an order. Full prompt, response and Ollama timing/token fields are saved in `work/verification/autotrader-latency.json`. This is one observed latency, not a guaranteed response time or evidence of strategy profitability.

The actual one-shot paper loop subsequently completed decision `625e0bccf27f4e05b8366f25a7cf2b16` in 11.844 seconds including completion polling. Laya selected HOLD; the paper account remained flat at 10,000 USDT. The full suite passes 59 tests, including 15 dedicated bot tests and the monitor's read-only artifact routes. JavaScript syntax and the PowerShell launcher syntax pass.

The new monitor routes and data contracts were verified directly with handler/database tests. Local browser access was disabled in Work settings, and the existing server at port 8900 was an older process without the new route. Restart that dashboard process from the current source before opening the Auto trader panel; an end-to-end browser check of the new panel was not available in this session.
