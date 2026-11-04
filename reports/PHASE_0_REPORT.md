# Phase 0 — Setup and baseline

Date: 2026-11-04 (Asia/Calcutta). Branch: `verified-fleet`.
Baseline HEAD: `75d915e3f07ae209ce4b5691977c5fdd18dd8be9`.

## Scope and status

This phase recorded a fresh restricted baseline. It is not a trading-readiness approval. No production bot was launched, stopped, or reconfigured. No exchange order, external request, model generation, dependency installation, or production database mutation was performed by this phase.

| Item | Status | Evidence |
| --- | --- | --- |
| 0.1 Workspace and approved branch plan | PASS | `git switch verified-fleet` followed by `git merge --ff-only laya-decision`: `Updating e23ee1a..75d915e`, `Fast-forward`, `1 file changed, 11 insertions(+)`; branch comparison immediately afterward: `0 0` |
| 0.2 Master instructions and status | PASS | Source body saved verbatim in `docs/MASTER_PROMPT.md`; byte comparison returned `True`; all phases initialized NOT RUN before observed Phase 0 updates |
| 0.3 Safe full-suite baseline | PASS, restricted scope | `python -B scripts/run_isolated_tests.py`: `collected 227 items`; `214 passed, 13 skipped in 25.51s`; `EXIT_CODE=0` |
| 0.4 Unrestricted external-service tests | NOT RUN | No approval for external-service requests. Four Binance checks and one CoinGecko check skipped explicitly |
| 0.5 Optional-environment tests in default interpreter | NOT RUN | Seven tests skipped because the optional backtesting package is not installed in the default interpreter; no installation attempted |
| 0.6 Credential-backed leak check inside disposable copy | NOT RUN | One existing test skipped because real credential files are deliberately excluded. Phase 1 will perform a safe local scan without copying credentials |
| 0.7 Local Ollama prerequisite | PASS | Read-only `GET http://127.0.0.1:11434/api/version`: `Ollama local health: 200 0.40.14` |
| 0.8 Account-size prerequisite | PASS for default selection | Local configuration check: `ACCOUNT_SIZE_USD: DEFAULT 1000 (not persisted)`; no production setting changed |
| 0.9 Exchange authentication prerequisite | NOT RUN | Required configuration is present locally; presence does not establish current exchange authentication. No credential-bearing request was made |

## Test isolation and interpretation

The test sources were reviewed for networking and writes before execution. The suite includes external requests, synthetic exchange callbacks, temporary databases, account fixtures, and a dashboard subprocess. It is therefore run only through `scripts/run_isolated_tests.py`.

The runner copies source and archived candle fixtures into a retained disposable directory, excludes production accounts and credentials, sanitizes inherited application settings, disables bytecode/cache writes, blocks external/model requests, and confines Python mutations to the copy. Local temporary HTTP test servers are permitted. Broker/exchange fixture results are stub-based unit/regression evidence, not exchange integration evidence. Historical candle replay is isolated replay evidence, not a new market-data download or full real-exchange execution.

Exact command:

```text
python -B scripts/run_isolated_tests.py
```

Redacted result summary:

```text
platform win32 -- Python 3.12.10, pytest-9.2.0
collected 227 items
214 passed, 13 skipped in 25.51s
EXIT_CODE=0
```

The runner retained `test-output.txt` and `pytest.log` in `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-y0dg41u9`. A background HTTP-fixture exception header appeared in output although the test run exited zero; its cause is not established by this report.

## Prerequisites and remaining risks

- Ollama is running. No model inference was attempted.
- Account size defaults to 1000 until supplied through the approved environment mechanism.
- Current exchange authentication remains unverified. Do not send credentials through chat.
- Known emergency-halt, exchange-close/reconciliation and protective-stop defects remain. This baseline does not establish that trading is safe.
- No Phase 2 or later work is authorized. Phase 1 is the next permitted phase.
