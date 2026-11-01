# Repository feature integration

The newer [four-repository integration review](FOUR_REPOSITORY_REVIEW.md) extends this milestone with Vibe-Trading-inspired strategy drafts, executable quantitative validation and optional Kronos forecasting. The current feature map is `config/features.json`; the verification counts below describe the earlier milestone.

The current request is tracked against the three repositories already supplied: TradingAgents, QuantJourney and CloddsBot. `config/features.json` is the machine-readable feature-family matrix exposed by `/api/features` and the dashboard's Integration coverage panel. It does not claim every upstream strategy, messaging channel or skill has been ported.

## Connected in this milestone

- Existing TradingAgents-inspired Laya research: parallel analysts, bull/bear debate, trader, three risk reviews, portfolio manager, schemas and audits.
- QuantJourney baseline backtests against saved Binance snapshots. Both EMA trend and buy/hold baselines use the installed simulator with next-bar order eligibility, fees, slippage, spot accounting and explicit final liquidation.
- Clodds VaR/CVaR and sequential volatility diagnostics calculated from the backtest NAV history. These report per-bar amounts using explicit USDT/USD parity for comparison; they are not live-account risk estimates.
- Dashboard backtest history, net return/drawdown/fees, report inspection/download, advisory risk view, and source-feature coverage.
- Persistent paper-entry pause/resume control, independent of process lifetime. Exits remain permitted while entries are paused. There is no timer-based automatic release.

## Run

```powershell
# Verification remains available with no arguments.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting

# Synthetic baseline backtest, separate from real research reports in the UI.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting run --demo

# Evaluate the actual archived candles of an earlier run.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting run --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json

# Alternative comparison baseline.
.\work\environments\backtesting\Scripts\python.exe -m cryptoscope.backtesting run --snapshot data/snapshots/21c193c8af0448ed8eccb53d80b85f08.json --strategy buy_hold_baseline

# Entry controls for the real paper ledger (no exchange orders).
python -m cryptoscope.research pause-entries
python -m cryptoscope.research resume-entries

python -m cryptoscope.dashboard --port 8900
```

Open `http://localhost:8900`. Restart an older dashboard server to load the new Python endpoints. Refresh alone reloads static browser assets, but cannot update a Python process that was already running.

Backtest artifacts live under `reports/backtests/<run-id>/`: `report.json`, `equity.csv`, and `summary.md`. Every report includes the input/config fingerprint, source, engine version, assumptions, fill times, decision availability times, metrics and equity history. The calculation processes only bars already known at each callback; EMA lines use causal exponential weighting. Earlier signals must not change when later candles are perturbed.

The EMA and buy/hold runs are deterministic strategy baselines, not Laya replays. Live Laya inference is never rerun on past data by this command. It does not use future news or reflections. Replaying Laya requires time-bounded research evidence plus the actual response-availability timestamp and a separate latency-aware execution policy.

## Remaining feature families

Next research work: automatic checkpoints/resume, settled-outcome memory, historical Laya replay, walk-forward optimization, advanced order lifecycle, more data sources and full portfolio attribution.

Next operations work: persistent research jobs, streaming data, freshness/reconnect handling, alerts, continuous stops, venue-aware circuit breakers, daily-loss/drawdown policies and multi-asset allocation.

Broader Clodds capabilities still pending: exchange execution, derivatives/funding/liquidation accounting, arbitrage, copy trading, TWAP/DCA, wallets/DEXs, messaging channels, prediction markets and Bittensor. Account-backed adapters require the corresponding account/venue/channel configuration. No external accounts, messaging destinations, wallets or trading permissions have been configured by this milestone.

The status names are deliberate: `implemented` means connected in Zien, `available_upstream` means installed library capabilities that are not yet exposed as Zien workflows, `pending` means implementation remains, and `needs_configuration` means the feature also depends on user-specific service setup.

## Verification on 2026-10-31

- Core Python suite: 23 passed, 4 optional backtesting tests skipped, 11 subtests passed.
- Backtesting environment integration suite: all 6 passed, including the 4 skipped by the core environment. Checks cover next-bar fills, cash/fee reconciliation, causal signals, reproducible fingerprints and saved artifacts.
- Clodds Node suite: all 7 passed, including reviewed source hashes, known loss calculations, sequential volatility calibration and invalid-input refusal.
- Optional environment `pip check`: no broken requirements. Dashboard JavaScript syntax check passed.
- Browser: backtest report inspector, feature map, desktop layout and 390px mobile layout verified; no console warnings/errors. Research table scrolling stays inside its panel.
- Archived Binance example `9b91dc237f0c48bfbd5bd0c07c0869c5`: 6 fills, -0.28976% net return, 0.36148% maximum drawdown, 5.97386 USDT fees. This is a baseline execution example, not evidence that Laya or this strategy is profitable.

Full repository parity remains unfinished. This earlier milestone recorded 13 implemented families out of 34 tracked families. The current matrix includes the later repositories and describes missing work rather than placeholder implementations.
