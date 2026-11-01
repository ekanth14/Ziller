# Crypto research integrations: four-repository review

Reviewed on 2026-10-31 against immutable source revisions. These additions extend the existing TradingAgents-inspired Laya workflow and the installed QuantJourney engine. The local dashboard is a monitor; research and simulations are started through the CLI.

| Source | Reviewed revision | Role in Zien |
| --- | --- | --- |
| [CloddsBot](https://github.com/alsk1992/CloddsBot/tree/c930628c47a4a745f497e29035a3b64622f97cc7) | `c930628c47a4a745f497e29035a3b64622f97cc7` | Existing vendored risk modules and validated advisory bridge |
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/78fab6b3f998583f640820db60c155ffa5641a62) | `78fab6b3f998583f640820db60c155ffa5641a62` | Constrained natural-language strategy drafts, versioned artifacts, crypto-calendar statistics |
| [Everything Claude Trading](https://github.com/brainbytes-dev/everything-claude-trading/tree/9a8fcfcaacd7620afc24dc8c5e79d922135f3e11) | `9a8fcfcaacd7620afc24dc8c5e79d922135f3e11` | Executable walk-forward, transaction-cost stress, comparison and block-bootstrap workflows |
| [Kronos](https://github.com/shiyu-coder/Kronos/tree/67b630e67f6a18c9e9be918d9b4337c960db1e9a) | `67b630e67f6a18c9e9be918d9b4337c960db1e9a` | Optional local OHLCV forecasting, supplied as evidence to Laya |

## What the source code shows

### CloddsBot

The reviewed revision is unchanged from the prior installation. Its scope spans crypto exchanges, prediction markets, chain/wallet operations, agent channels, execution and risk tools. Zien retains the selected VaR/CVaR, volatility and heuristic stress modules under `integrations/clodds-risk/`, with their original MIT license and blob-hash checks. The rest of the app and its dependency tree are not installed. See [the detailed review](CLODDSBOT_REVIEW.md) for inspected implementation limitations.

### Vibe-Trading

Version 0.1.18 is a complete application with a Python research runtime, tool registry, multiple market adapters, backtesting, paper accounts, persistent artifacts, an API and React UI. Reviewed files include `pyproject.toml`, `agent/backtest/engines/crypto.py`, `agent/backtest/models.py` and `agent/backtest/metrics.py`.

Its crypto engine distinguishes spot from perpetual funding and has additional strict perpetual risk/accounting paths. Its metrics use a 365-day calendar for crypto rather than the equity convention of 252 trading days. Those distinctions matter; copying the generic financial defaults would produce misleading crypto results.

Zien implements its own small strategy studio inspired by the natural-language research and artifact workflow. Laya returns a typed definition for an EMA or buy/hold template, which is validated before it can reach the existing backtester. Unsupported requests are refused. Generated Python, shell commands and model-selected risk-limit changes are not supported. Drafts preserve the request, model audit, version fingerprint and original definition.

The full Vibe application is not a drop-in dependency: its `backtest` module also differs from QuantJourney's `backtester`, and it brings a separate provider/runtime, large market-data dependency set and web stack. Importing the whole app would not connect those features to Zien's accounting or decision contracts. No Vibe source code is vendored by this milestone.

### Everything Claude Trading

The repository contains agent descriptions, trading-domain skills, commands, rules and worked examples for Claude Code. Its README is a capability catalog, not an executable implementation of every named financial method. Actual paths include `agents/crypto-defi-analyst.md`, `skills/backtesting/walk-forward-optimization/SKILL.md`, `skills/backtesting/strategy-evaluation/SKILL.md` and `rules/common/data-integrity.md`.

Zien translates selected research practices into tested code: train-only EMA selection, chronological test windows with an embargo, matched buy/hold comparisons, 1x/2x/3x transaction-cost stress, and seeded circular block resampling of net equity returns. Undefined Sharpe/Sortino ratios remain null. Bootstrap results are explicitly descriptive; they do not certify future profitability. General risk thresholds in reference prompts are not adopted as universal deployment rules.

The Claude plugin is not installed into the user's global agent configuration. Its prompts do not replace Laya. Specialized financial models, portfolio optimization, CPCV and deflated-Sharpe calculations remain outside this milestone.

### Kronos

The repository supplies PyTorch inference code, pretrained model identifiers, examples and separate fine-tuning pipelines. It has no Python packaging metadata suitable for a direct `pip install` from GitHub. Zien vendors only `model/__init__.py`, `model/kronos.py`, `model/module.py` and `LICENSE`, preserving semantics and normalizing line endings. Tests verify the pinned Git blob contents under that normalization.

Kronos-small uses the base tokenizer and a 512-bar context. The isolated worker uses CPU inference, a bounded horizon and sampling count, and explicit random seeds. The predictor averages sampled paths; that output is not a calibrated probability or a prediction interval.

Downloads use the official NeoQuasar model repositories and record exact model revisions in `data/models/kronos/manifest.json`. Subsequent setup runs reuse those revisions. Only model configuration and safetensor weights are fetched. Inference loads local paths with `local_files_only=True`; it does not fetch models during a research run.

Only closed snapshot candles enter the model. Timestamp calendar fields use UTC. Older Zien snapshots contain base volume but no quote turnover; the reviewed predictor derives its documented amount proxy from mean OHLC times base volume. That approximation is recorded in each artifact.

Forecasts are validated for snapshot hash, symbol, finite positive OHLC, candle geometry, horizon and consecutive timestamps. Both the input cutoff and actual inference availability are saved. A forecast made today from an old archive is an analysis of that archive, not evidence that was available historically. Historical Kronos evaluation must also address model-training overlap with the test period.

## Ownership and commands

| Location | Responsibility |
| --- | --- |
| `cryptoscope/forecasting/` | Model download, isolated worker, validated evidence and forecast CLI |
| `integrations/kronos/` | Reviewed inference source, license and source provenance |
| `work/environments/kronos/` | Isolated CPU inference dependencies |
| `data/models/kronos/` | Local weights, cache metadata and pinned model manifest |
| `cryptoscope/strategy/` | Typed Laya strategy drafts; no arbitrary code execution |
| `cryptoscope/backtesting/validation.py` | Walk-forward, comparison, cost stress, bootstrap and statistics |
| `reports/forecasts/`, `reports/strategies/`, `reports/backtests/` | Versioned artifacts consumed by the monitor |

Run from the project root in PowerShell:

```powershell
# Install optional inference dependencies and download the official weights.
.\scripts\setup-kronos.ps1

# A standalone forecast from an archived input (not a historical replay).
python -m cryptoscope.forecasting run --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json --steps 12 --samples 3

# Fresh public data -> optional Kronos evidence -> existing Laya research.
python -m cryptoscope.research --config config/local-cpu.json analyze --live --symbol BTCUSDT --kronos

# Natural-language request -> typed strategy draft.
python -m cryptoscope.strategy --config config/local-cpu.json draft --request "BTCUSDT spot EMA trend baseline with fast 10 and slow 30" --symbol BTCUSDT

# Substitute the report path printed by the draft command.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting run --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json --strategy-spec reports/strategies/7c88880cfce3455a8cacffb0fc4389a5/report.json

# Rolling training/test windows with a two-bar embargo.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting walk-forward --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json --train-bars 100 --test-bars 40 --embargo-bars 2

# Matched comparison, cost stress and seeded block bootstrap.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting validate --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json

python -m cryptoscope.dashboard --port 8900
```

Open `http://localhost:8900`. Restart an older dashboard server to load the new API routes. The monitor shows research, standalone forecasts, strategy drafts and baseline/validation reports. Demo artifacts remain separate from real-input artifacts.

Walk-forward windows start flat, use past bars for EMA warmup without permitting pre-test entries, liquidate at each fold's final open and compound the resulting test returns. Only complete non-overlapping test windows are included. A small predeclared parameter grid does not eliminate selection bias, and the short bundled archive is insufficient for a profitability claim. Neither the strategy drafts nor these backtests automatically change the paper trading strategy.

## Remaining scope

This is not full feature parity with any of the upstream applications. The dashboard's feature map (`config/features.json`) separates connected workflows from remaining work. Broad chat/tool execution, dynamic strategy code, perpetual account simulation, live exchange execution, wallet/DEX operations, additional channels, model fine-tuning and full quantitative skill coverage still require implementation and, where applicable, account-specific setup. Installing a library or copying a skill description does not mark its feature implemented.

## Verified artifacts and runtime checks

- Kronos-small and its base tokenizer are installed in the optional CPU environment. `requirements-kronos-lock.txt` captures the complete installed dependency set; both optional environments pass `pip check`.
- Official weight revisions: tokenizer `0e0117387f39004a9016484a186a908917e22426`, model `901c26c1332695a2a8f243eb2f37243a37bea320`.
- A real local 12-bar, three-sample forecast from 200 archived Binance candles completed as artifact `d48997041bc24ad4897b6444f44ba5a3`. The worker used local model files. Its horizon belongs to the archive's cutoff and is not a current price forecast.
- Actual Laya strategy draft `7c88880cfce3455a8cacffb0fc4389a5` selected EMA periods 10/30. Matching baseline backtest `053801a93bc54dcd96b3704ce0b1a97a` completed with six fills and -0.05586% net return after costs. The draft remains immutable; the monitor links the matching backtest separately.
- Walk-forward artifact `2f11c97fed314b438527a671ec22074e` contains two complete out-of-sample windows, six fill records, -0.14138% compounded return and 5.99195 USDT fees. Training choices, test boundaries and scaled fills are recorded.
- Robustness artifact `7fe96b6a956e45a3ae75bbe28d2e1698` records matched buy/hold comparison, cost multipliers 1/2/3 and seeded block resampling.
- The first fresh-data end-to-end run, `9a878f9cc65349bfa7c9633fb8e4b32d`, generated valid Kronos evidence and reached Laya's risk-review stages. Ollama then returned unfinished JSON while reporting `done_reason=stop`. The run failed with no decision or execution. The provider now allows one audited regeneration for incomplete/malformed JSON; it does not repair or use the partial output. Dedicated tests cover successful recovery, bounded repeated failure and no retry of network errors.
- Browser verification covers forecast and strategy inspectors, robustness report fields, 390px mobile layout, and no console warnings/errors. The model-health display distinguishes a delayed check from a refused connection.
- The complete Python suite passes all 43 tests when run with the optional backtesting environment, including chronological validation, forecast handoff, source provenance, accounting, local schema validation and bounded Laya retry checks. The core environment passes 36 tests and 28 subtests, with seven optional-engine tests skipped there. All seven Clodds Node tests pass. JavaScript and PowerShell setup syntax checks pass.
- A later run exposed a zero `reduce_fraction` despite the generation schema. Responses now pass local validation of required fields, types, allowed evidence, bounds, list lengths and text lengths. Schema violations receive the same single audited regeneration attempt. Invalid output is never silently coerced into a valid trade proposal.
- Final fresh-data run `d29b6710165a47e58463f2c6fc464450` completed all seven research stages in approximately 482 seconds. It produced an actual Kronos forecast and made eight local Laya calls: the trader's first response failed the numeric schema and its single regeneration passed. All other roles passed on their first calls. The portfolio manager rejected the proposal; execution was `rejected_by_laya`, with no error. The paper ledger remained at 10,000 USDT, zero positions and zero fills.
- The final localhost API check confirmed that completed run, its seven stages, forecast and rejected decision are available in the monitor. Final browser recapture was unavailable after local browser access was disabled in Work settings; the earlier browser checks and final API checks are recorded separately.

Passing JSON validation establishes structural correctness, not research quality. In the final run, some concise text was still a sentence fragment and the portfolio manager explicitly declined the proposal on that basis and on weak evidence. That rejection is preserved; it is not replaced with an approval or a claim of model accuracy.
