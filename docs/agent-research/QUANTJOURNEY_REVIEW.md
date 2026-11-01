# QuantJourney integration review

Reviewed on 2026-10-31. Source: [QuantJourneyOrg/quantjourney-bt](https://github.com/QuantJourneyOrg/quantjourney-bt), revision [`4f403d853833e1daa6de01c5b6c6cb3983dc0044`](https://github.com/QuantJourneyOrg/quantjourney-bt/tree/4f403d853833e1daa6de01c5b6c6cb3983dc0044), version 0.12.5, Apache-2.0, Python >=3.11. The source labels the project Alpha. This is a focused architecture/dependency review, not an audit of every file.

## Fit for Zien

Use QuantJourney as an optional local historical simulation and evaluation engine. Keep Laya as the decision model and the existing Zien broker as the paper execution component. Installation alone does not connect Laya decisions to historical replay or add backtesting to the dashboard.

| Upstream component | Value for crypto research | Zien treatment |
| --- | --- | --- |
| `execution/FillEngine` | Market, limit, stop, trailing, bracket and OCO lifecycles; commissions/slippage | Installed and exercised through the shared simulator |
| `execution/ExecutionSimulator` | Processes pending fills before the strategy callback, making submitted orders next-bar eligible | Verified with two synthetic BTCUSDT fills |
| `portfolio/accounting/PortfolioLedger` | Cash, fractional positions, average entry, NAV and exposure | Explicit USDT settlement and crypto contract specification |
| `execution/ContractSpec.crypto` | Fractional sizes, tick size and quantity-step support | Use venue-specific metadata; do not assume its defaults match Binance |
| `risk/PreTradeRisk` | Configurable margin utilization, gross exposure, shorting and pending-order reservations | Defaults are permissive; verification explicitly disables shorts and sets limits |
| `risk/`, portfolio rebalance and strategy book | Position caps, volatility targeting, risk parity and allocation | Available for later multi-asset strategy evaluation |
| Walk-forward and optimization | Rolling/expanding/anchored validation, purge/embargo, grid search | Available in core; Optuna extra deferred until needed |
| Metrics and static reports | Local CSV/JSON, charts and HTML research reports | Dependencies installed; a Zien dashboard adapter is still required |
| Cloud SDK and high-level data preparation | Authenticated QuantJourney data service | No credentials configured; no account or subscription created |

Evidence: [public scope](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/docs/public_scope.md), [simulator](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/backtester/execution/simulator.py), [contract specs](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/backtester/execution/contract_spec.py), [risk controls](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/backtester/risk/pre_trade.py).

## What was installed

The core package and its mandatory dependencies are installed in `work/environments/backtesting/`. The main bot and dashboard remain runnable with the standard library. `requirements-backtest.txt` pins the source commit; `requirements-backtest-lock.txt` records all resolved versions for the verified Windows/Python 3.12 environment.

Core dependencies include NumPy, pandas, SciPy, matplotlib, seaborn, QuantJourney technical indicators, HTTPX, requests, Pydantic, psutil, dateutil, questionary and rich. Indicator dependencies also pull in Numba and llvmlite. We install the supported whole package rather than copying source modules with incomplete dependencies. The old standalone `requirements.txt` upstream omits CLI dependencies present in `pyproject.toml`; package metadata is authoritative.

Skipped optional extras: `data` (yfinance fallback; Zien already uses Binance), `wf` (Optuna optimization), `dev` (upstream release/lint/testing tools), and `typecheck`. These are not prerequisites for Zien's current crypto research bot.

## Commands

From the project root in PowerShell, no activation or execution-policy changes are required:

```powershell
# Repeat the offline crypto execution/accounting verification.
.\work\environments\backtesting\Scripts\python.exe -B -m cryptoscope.backtesting

# Confirm dependency consistency.
.\work\environments\backtesting\Scripts\python.exe -m pip check

# Reinstall the exact verified dependency versions, if needed.
.\work\environments\backtesting\Scripts\python.exe -m pip install -r requirements-backtest-lock.txt

# First-time setup helper; resolves required dependencies from the pinned source.
powershell -NoProfile -File .\scripts\setup-backtesting.ps1
```

The verification is synthetic, fully offline and uses no Laya inference or exchange trading endpoints. It writes `work/backtesting/verification.json`. It checks 0.01 BTC sizing, quantity rounding, next-bar execution, 10 bps fees, 5 bps slippage, flat final inventory, and exact cash/NAV reconciliation. Its tiny synthetic return says nothing about strategy profitability.

## Crypto-specific work still needed

1. Adapt archived Zien/Binance candles into aligned UTC OHLCV frames, retaining closed-bar cutoffs and missing-data behavior. Bind each Laya proposal to its actual availability timestamp, including inference latency; filling before the response existed would leak future information.
2. Use actual exchange quantity steps, minimum notional, tick size and fee tiers. The explicit contract in the installation check is illustrative, not fetched exchange metadata.
3. Keep spot and perpetual accounting separate. Generic futures/inverse contract helpers do not establish a complete perpetual funding, maintenance-margin, liquidation or insurance-fund model. Those features have not been validated by this review and are not added to Zien by installing the package.
4. Set annualization explicitly for crypto research. `infer_periods_per_year` heuristically chooses 365 vs 252 based on weekend presence and observed bars per day. A weekday-only or partial-day sample can misinfer 24/7 crypto cadence. For complete 15-minute 24/7 data the intended rate is 365 * 96 = 35,040 observations per year; daily reporting defaults elsewhere still use business-day conventions.
5. Validate intrabar ambiguity for bracket exits. The fill engine documents stop-before-limit ordering when both levels are reachable; OHLCV does not reveal the exact price path. No tick/order-book replay was installed.
6. Add out-of-sample comparison against simple baselines and the existing deterministic signal layer, after all fees and slippage. The upstream examples primarily target stocks/ETFs, FX and conventional futures; they are templates, not ready-made BTC/ETH strategies.

The high-level `Backtester` uses QuantJourney cloud for ordinary data preparation/authentication; hosted runs require the documented product entitlement and API scopes. The lower-level simulator/ledger and bundled sample-data path work locally without credentials. No API key is required for the installed verification.

References: [installation metadata](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/pyproject.toml), [README and cloud access](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/README.md), [Windows guide](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/WINDOWS.md), [reporting frequency](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/backtester/reporting_frequency.py), [fill-engine assumptions](https://github.com/QuantJourneyOrg/quantjourney-bt/blob/4f403d853833e1daa6de01c5b6c6cb3983dc0044/backtester/execution/fill_engine.py).
