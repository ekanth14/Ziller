# Phase 3 final handover — November 9, Asia/Calcutta

Branch `verified-fleet`. **Verdict: PARTIAL / NOT COMPLETE.** The operations repairs, real bounded Spot Testnet lifecycle, and safe regressions are complete within their stated scope. Phase 3's real partial-fill and HTTP 429 cases were not observed; therefore the full exchange integration gate did not pass and no seven-day run started. The sections below retain earlier observations as historical evidence; this section supersedes their former order-approval and order-NOT-RUN statements. Phase 4 and LIVE remain untouched.

| Item | Latest observed result | Limit |
| --- | --- | --- |
| Model benchmark | PASS, approved installed `gemma4-quant:12b` substitution | Two real 30-scenario runs; no predictive-edge claim. |
| Thirty-minute operations soak | PASS under criterion recorded before the fresh run | Fifty SSE workers, zero load failures, graceful shutdown; isolated dashboard only. |
| Databases and backups | Prior PASS retained | Thirteen working WAL databases and verified restores; no new production migration in this follow-up. |
| Spot Testnet bounded lifecycle | PASS for the approved BTCUSDT diagnostic | Real limit buy canceled unfilled, market buy filled, exchange STOP_LOSS rested then was canceled, and HALT_FLATTEN market sell filled. No position or owned open order remained. |
| Real partial fill / HTTP 429 | NOT OBSERVED | No deliberate rate-limit flooding or forced partial fill. Stub tests pass, but those are not venue integration. |
| Seven-day Testnet run | NOT RUN | Requires complete real integration; no unattended trading was launched. |
| Dashboard readiness | Source tests PASS; refreshed process started | New OBSERVE launcher printed localhost:8900. The post-restart HTTP check could not run because automatic approval review hit a usage limit; current response is unverified. |

The user separately approved the bounded Testnet order diagnostic. Command: `python -B scripts/run_phase3_testnet_checks.py --execute-approved-checks` with its explicit approval flag, followed by the retained-copy resume, inspection, filter recheck and ledger reconciliation. These ran against official Binance Spot Testnet only, using the isolated diagnostic state. Entry limit order **11618421** was CANCELED with zero execution; market buy **11618423** FILLED 0.00026000 BTC; protective STOP_LOSS **11618424** was observed NEW for the same amount and later CANCELED unfilled; close market sell **11620699** FILLED 0.00026000 BTC. The process restart was forced only after the protective order was confirmed. Restart reconciliation and HALT_FLATTEN each reported PASS; emergency halt remained engaged and entry disabled. Signed read-only inspection then found zero BTC open orders. The disposable SQLite ledger ended at schema version 2 with zero position rows and all four owned order rows terminal. No LIVE order or other account order was touched. Evidence: `reports/PHASE_3_REPAIR_EXCHANGE_RESULT.json`; retained raw disposable state `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-uzj7jgi0`.

The diagnostic's first restart stopped before flatten because its network audit blocked Windows' local event-loop socket. The retained, exchange-resting stop was inspected by exact order ID before any retry. A later restart stopped on the already engaged HALT_FLATTEN latch; read-only inspection confirmed the own stop still matched the recorded 0.00026 BTC. The corrected resume canceled that stop and sold the exact tracked quantity once. A malformed minimum-notional test value initially yielded `-1100`; a properly formatted nonexecuting recheck yielded `-1013`. The lot and tick cases also yielded `-1013`. These interruptions are part of the evidence, not hidden successes. They did not create a second buy. The final result is bounded-lifecycle PASS, full-Phase-3-integration NOT_COMPLETE, operator reconciliation not required, partial fill NOT_OBSERVED and rate limit NOT_OBSERVED.

Final full isolated suite before the last stop-ledger refinement: `python -B scripts/run_isolated_tests.py`, **390 collected, 378 passed, 12 skipped, exit 0**, 68.26 seconds. Focused suite after that refinement: `python -B scripts/run_isolated_tests.py cryptoscope/tests/test_phase3_followup.py cryptoscope/tests/test_binance_testnet.py cryptoscope/tests/test_phase3_operations.py`, **34 passed, 4 skipped, exit 0**. The latter includes the added stop-ledger regression. The remaining source edits after the focused suite concern only the bounded diagnostic's nonexecuting filter/inspection and retained-ledger helpers; their real Testnet paths completed as described. No new full-suite result is claimed for the final exact tree. The final exchange result and model/soak/test evidence are in the `PHASE_3_REPAIR_*` files.

The old dashboard child was identified by its OBSERVE launcher and port, stopped, and replaced by a hidden OBSERVE-only launcher. Its stdout records `http://localhost:8900`; its stderr later records intermittent public quote/DNS errors. The immediate post-restart `/health` and `/ready` checks were rejected by automatic approval review because its usage limit was reached, so neither a healthy nor degraded current response is claimed. The running service was not restarted again. Existing sessions, production databases, backup copies, the master prompt and five-gate governor source were preserved.

**Handover:** Antigravity can continue from `verified-fleet` with the bounded Testnet state closed and the remaining Phase 3 work explicitly marked: observe genuine partial fills and 429 behavior safely, complete a final exact-tree test and localhost readiness check when tool review is available, then decide whether a seven-day unattended Testnet run is justified. Phase 1 remains unresolved and blocks Phase 4. LIVE must stay disabled.

# Phase 3 repair follow-up — November 8, Asia/Calcutta

Branch `verified-fleet`. The previous Phase 3 report remains below as historical evidence. **Current Phase 3 verdict: PARTIAL / NOT COMPLETE.** The new model and operations checks pass; real exchange-order integration and the dependent seven-day run remain NOT RUN pending separate approval and actual acceptance evidence. No Phase 4 work or LIVE activation was performed.

| Requirement | Latest result | Evidence and boundary |
| --- | --- | --- |
| 3.1 local model | PASS measurement with approved substitution | Real `gemma4-quant:12b`, not requested `gemma4:12b`; 30 identical historical scenarios in each of two runs, 60/60 valid JSON and schema, zero timeouts. Compact scored committee only; no trading edge inference. |
| 3.2 soak | PASS for the new prospectively recorded memory protocol | Real isolated dashboard, 1800 seconds, 50 SSE workers, 61 regular samples, zero load failures, graceful server exit. The previous REVIEW result and original numbers remain below. |
| 3.3 / 3.3b databases and backups | Prior PASS retained | Thirteen working WAL databases, verified backup/restores and hourly development worker. No new production DB migration in this follow-up. |
| 3.4 authentication | Prior PASS retained | The two previously approved read-only authenticated GETs returned HTTP 200; no new authenticated request here. |
| 3.4 real order lifecycle | NOT RUN | Bounded BTCUSDT Testnet diagnostic is prepared and previewed. Explicit separate order approval remains pending. Stub-based lifecycle regressions are not exchange integration. |
| 3.4 seven-day run | NOT RUN | Real integration has not passed; no unattended order process started. |
| 3.5 readiness | PASS isolated source behavior; existing service check pending | `/ready` returns HTTP 503 when required feeds or verified BTC/ETH/SOL prices are unavailable, and exposes `trading_authorized=false`. REST status labels now describe REST adapters. Current localhost process must be checked separately for loaded source. |
| 3.6 spec | Prior PASS retained | Master prompt and five-gate governor are unchanged. |

## Commands and fresh evidence

`python -B scripts/run_phase3_benchmark.py` exited 0. The real local model used the frozen Phase 2 scored-committee inputs and settings, with no cached responses. Run 1 (30 scenarios): p50 9.381703 s, p95 10.105325 s, valid JSON/schema 30/30, timeouts 0/30, mean generation throughput 6.855412 tokens/s. Run 2 (30 scenarios): p50 9.262810 s, p95 10.172263 s, valid JSON/schema 30/30, timeouts 0/30, throughput 6.934235 tokens/s. Run 2 minus run 1 p50 was -0.118893 s and p95 +0.066938 s. Maximum of the 60 request times was 29.85 s. These observations do not establish that the transport alone caused the speed difference. Source: `reports/PHASE_3_REPAIR_BENCHMARK.json` and `.csv`; original disposable copy `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-l57o5x9c`.

The model transport now isolates local generation in its own credential-free worker, enforces the 35-second parent deadline and kills only its own worker on expiry. Incomplete generation and an opposite or invalid consensus direction fail closed. An isolated stuck-worker test exercises the deadline; the earlier 184-second timeout remains historical evidence, not an outcome of this new run. No Laya classifier training or Phase 8 work was started.

`python -B scripts/run_phase3_soak.py --duration 1800 --clients 50 --interval 30` exited 0 with status PASS. Its `phase3-private-memory-v2` criterion was saved in `soak-protocol.json` **before** the server and load started. The actual isolated server ran 1800 seconds, 61 samples, maximum sample gap 30.047 s, 50 SSE workers, 89,857 pre-shutdown frames, 8,724 successful API requests, zero pre-shutdown SSE/API failures, and exit 0 in 1.735 s. Second-half private-memory slope +0.007019 MiB/minute, range 0.242188 MiB; RSS slope +0.006924 MiB/minute. Both the new private-memory rule and the original RSS plateau field passed in this new run. Close-connection HTTP/1.1 microbenchmark: 100/100, 100 TCP connections, 88.16 requests/s; keep-alive: 100/100, one TCP connection, 1548.35 requests/s. These loopback rates are not production capacity estimates. Source: `reports/PHASE_3_REPAIR_SOAK.json`, `.csv`, `_PROTOCOL.json`; original disposable copy `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-6pkithf6`. This copy predates subsequent exchange and readiness edits; the soak exercises the unchanged dashboard load routes, not those later behaviors.

`python -B scripts/run_isolated_tests.py` with approved local socket access: **390 collected, 378 passed, 12 skipped in 68.26 s, exit 0**. The suite ran in a disposable copy with external/model requests blocked and no real credentials or orders. Five skips are external checks; seven need optional QuantJourney. Stub exchange tests verify cumulative fee accounting, partial close/restart without duplicate sell, lost entry recovery without a duplicate buy, retained dust, rate-limit cooldown, stop request shape, halt preservation and degraded readiness. They do not prove real venue behavior. Output: `reports/PHASE_3_REPAIR_TEST_OUTPUT.txt`; disposable copy `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-ig2c1rvl`. A sandboxed attempt had local event-loop/socket problems and was stopped; the final authorized run is the result above. `git diff --check` found no whitespace errors.

The new Testnet diagnostic preview is `python -B scripts/run_phase3_testnet_checks.py` (preview only). The proposed bounded execution is BTCUSDT on official Spot Testnet, at most 40 USDT total buy notional plus fees: own limit order/query/cancel, one quote-capped market buy, actual fill/fee accounting, resting exchange STOP_LOSS, forced restart of the isolated diagnostic process, read reconciliation, HALT_FLATTEN of tracked exposure, and three nonexecuting filter checks. It refuses existing BTC open orders and leaves ambiguous exposure halted for operator review. It does not deliberately force rate limits or promise a partial fill; those cases remain NOT OBSERVED if absent. The execute path requires a separate explicit approval and was **not run**. No seven-day run can be accepted from the preview.

The original Phase 3 report follows; its measurements and limitations are retained without rewriting them.

# Phase 3 operations and exchange verification

November 7, Asia/Calcutta. Branch `verified-fleet`. Phase 3 commits: `e0b899c` (SQLite/HTTP/telemetry), `bdd20ed` (execution safety), `daaf237` (listings), `c0359f8` (benchmark), `c939ed0` (spec), `5bb2144` (empty-backup guard). **Overall Phase 3 verdict: PARTIAL / NOT COMPLETE.** Authorized checks are collected; real order lifecycle is NOT RUN and the frozen memory-plateau criterion was not met. No Phase 4 work started.

The user authorized the installed model substitution, WAL migration of five named working databases after verified backups, and two read-only Binance Spot Testnet authentication checks. No exchange order, account cancellation, training, dependency installation, LIVE activation or Phase 4 job has run. Phase 2 retains its scoped historical integrity PASS; Phase 1 remains unresolved.

| Item | Result | Evidence and limits |
| --- | --- | --- |
| 3.1 | PASS measurement with approved substitution | Two real runs of 30 historical scenarios on `gemma4-quant:12b`; requested `gemma4:12b` was not installed or tested. Each run has one timeout. This measures the compact scored committee, not the longer production consensus prompt. |
| 3.2 | REVIEW; load and shutdown checks PASS, frozen plateau criterion not met | Repaired run completed 1800.016 seconds with 50 SSE workers, zero load failures, 61 samples and exit 0 in 2.36 seconds. Late RSS decline makes second-half absolute slope exceed the frozen threshold. |
| 3.3 | PASS working-database checks; archival exception | All 13 working databases are WAL. Two immutable archival copies remain DELETE. Inventory, per-connection policy, five active sessions and journal counts are documented below. |
| 3.3b | PASS snapshots and restore checks; automatic scheduling verified on an isolated fixture | Three actual 13-database snapshot batches restored separately and verified. Hourly worker is running; it is not an installed Windows service. |
| 3.4 authentication | PASS real read-only integration | API-key-header historical-trades GET and signed account GET each returned HTTP 200. Account response was discarded. |
| 3.4 order lifecycle | NOT RUN against exchange | Market/limit orders, real partial fills/filter rejections/rate limits, resting protection, forced process restart and HALT_FLATTEN have no order-placement approval. Safety repairs have isolated stub-based coverage only. |
| 3.4 seven-day run | NOT RUN | Full exchange integration has not passed; no unattended trading job was launched. |
| 3.5 | PASS observations, with readiness limits | Running localhost health/readiness return 200; eight ticker symbols and 86 listings (50 on page 1) were observed. Versioning status and actual filtering scope below. |
| 3.6 | PASS spec correction | README and architecture now reflect the actual activation gates, default thresholds, confirmation and users.db name. Protected governor source is unchanged. |

## Commands and regression evidence

`python -B scripts/run_isolated_tests.py`: **378 collected, 366 passed, 12 skipped in 63.31 seconds; exit 0**. Full output: `reports/PHASE_3_TESTS_FINAL.txt`. Disposable copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-0x721ygc`.

The guard excludes real environment files and account databases, confines filesystem writes to the disposable copy, disables bytecode/cache writes, and denies external/model requests. Five skips are external-service checks excluded by that guard; seven require the optional QuantJourney environment. These skips are not exchange failures or evidence of exchange-order integration. Existing governor, emergency state, Telegram, AST isolation and historical backtest tests passed. New `cryptoscope/ops` modules are covered by the AST execution-import restriction.

Focused follow-up: `python -B scripts/run_isolated_tests.py cryptoscope/tests/test_phase3_operations.py cryptoscope/tests/test_phase1_security.py cryptoscope/tests/test_server_endpoints.py cryptoscope/tests/test_orchestrator_execution.py cryptoscope/tests/test_telegram_gateway.py` returned **83 passed in 15.61 seconds**, using local sockets and exchange stubs only.

## Debate measurement

Command: `python -B scripts/run_phase3_benchmark.py`. Child exit 0; real local Ollama calls, no cached model responses. Thirty evenly spaced historical committee inputs were selected from the same 83-input Phase 2 archive, without future outcomes. The same 30 inputs were used twice. Protocol `phase2-scored-committee-v1`, temperature 0, seed 17, four CPU threads, context 512, output cap 40. Request timeout 34.5 seconds within the nominal 35-second stage budget; failures return STAND_ASIDE.

| Metric | Run 1 (30 scenarios) | Run 2 (30 scenarios) | Run 2 minus Run 1 |
| --- | ---: | ---: | ---: |
| p50 seconds | 14.043625 | 13.669174 | -0.374451 |
| p95 seconds | 14.548035 | 15.254703 | +0.706668 |
| Valid JSON | 29/30 (96.67%) | 29/30 (96.67%) | 0 percentage points |
| Valid schema within budget | 29/30 | 29/30 | 0 |
| Timeouts | 1/30 (3.33%) | 1/30 (3.33%) | 0 percentage points |
| Mean generation throughput, available responses | 4.789331 tokens/second | 4.740961 tokens/second | -0.048370 |

The throughput uses Ollama `eval_count / eval_duration`, not request throughput; available measurements exclude timed-out responses. The run-1 timeout took 34.579249 seconds; run-2 scenario 23 took **184.298153 seconds** before the caller regained control and returned timeout. The latter coincided with a large scheduling gap in the initial soak, but its cause is not established. This is evidence that the nominal request timeout did not enforce a hard wall-clock deadline on this host. It is not an acceptable 35-second successful decision. No output from that call was accepted as an actionable decision. p95 alone hides this outlier.

The host concurrently ran the initial isolated soak. These are throughput/format observations, with zero trading executions and no predictive-skill claim. The installed tag differs from the requested tag by explicit user choice; native Laya classifier work remains Phase 8 and was not started. `reports/PHASE_3_SOURCE_AND_MODELS.json` records the actual local model tags and byte equality between the repaired soak copy and current HTTP/telemetry source.

Evidence: `reports/PHASE_3_BENCHMARK.json`, `reports/PHASE_3_BENCHMARK.csv`; original private disposable outputs remain at `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-bvsikhqv`.

## Soak investigation

Command: `python -B scripts/run_phase3_soak.py --duration 1800 --clients 50 --interval 30`. Both runs used an actual isolated dashboard process, 50 real local HTTP SSE client workers and a separate steady API worker targeting approximately five requests/second. Outbound networking and model calls were blocked; this is dashboard operations load, not connected-exchange performance or trading readiness. The production dashboard on port 8900 was left running.

Initial run: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-2fw4nrn7`. Forty-three samples, 3486.782 elapsed seconds in the sampling result, with large gaps rather than continuous 30-second samples. It recorded 108 SSE failures and one API failure before shutdown; final counters also included shutdown disconnects. RSS rose from about 46.69 MB to peaks near 59.78 MB. Whole-run slope 0.298966 MB/minute. Its mathematical second-half slope of 0.042220 MB/minute was distorted by the long gaps and is not accepted as proof of a stable 30-minute run. Its recorded shutdown duration also spanned an extended interruption and is not a valid shutdown latency measurement. The server eventually exited 0. Overall result REVIEW, not PASS. The exact cause of the host interruptions and client failures is unknown.

Investigation independently reproduced retained native type growth: 100 metrics calls with the initial implementation added 100 retained ctypes pointer definitions; the repaired implementation added zero after initialization. Structure definitions are now cached once in `cryptoscope/ops/telemetry.py`. This also fixes the same per-request definition pattern formerly embedded in the dashboard. Evidence: `reports/PHASE_3_TELEMETRY_REGRESSION.json`.

The replacement run retains 30-second UTC samples, resource values and separate pre-shutdown/shutdown counters. It categorizes transport failures, measures actual HTTP response versions and connections, and rejects sampling gaps above interval plus five seconds. The frozen plateau criterion is second-half absolute RSS slope at most 0.1 MB/minute and range at most 10 MB. Native Windows RSS and owned IPv4/IPv6 TCP rows are measured directly; threads are observed Python threads, not a fabricated client count. Periodic SSE reconnection can briefly put the sampled active count below 50 while all 50 workers remain running.

Replacement result: **REVIEW**, collected with child exit 0. Disposable copy `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-og2ojr3l`. Evidence: `reports/PHASE_3_SOAK.json` and `reports/PHASE_3_SOAK.csv`.

| Measurement | Observed |
| --- | ---: |
| Load duration | 1800.016 seconds |
| Samples / maximum interval | 61 / 30.032 seconds |
| SSE worker clients / minimum sampled active connections | 50 / 47 during reconnection |
| Pre-shutdown SSE frames / failures | 89,868 / 0 |
| Pre-shutdown API successes / failures | 8,725 / 0 |
| Observed API load throughput | 4.847 successful requests/second |
| Initial / final RSS | 46.5625 / 40.464844 MB |
| Whole-run / second-half RSS slope | -0.047562 / -0.230951 MB/minute |
| Graceful exit / server shutdown latency | 0 / 2.360 seconds |
| HTTP/1.1 close-mode microbenchmark | 100/100 successful, 100 TCP connections, 80.106 requests/second |
| HTTP/1.1 persistent-mode microbenchmark | 100/100 successful, one TCP connection, 2363.591 requests/second |

RSS stayed near 47 MB through most of the run, then fell to approximately 40.46 MB near minute 29. The reason for that decrease was not established. The final second-half absolute slope exceeds the predeclared 0.1 MB/minute threshold, so `plateau=false` and overall status REVIEW are retained. This is not sustained positive growth; it does not justify claiming a remaining memory leak, and it is not a reason to retroactively relax the acceptance rule. A subsequent run should predeclare any additional committed-memory measurements and interpretation before testing. The fixed native type-retention defect remains independently reproduced and regression-tested.

The 50 disconnects and one API failure recorded **after shutdown was requested** are retained separately in `shutdown_counters`; they are not mixed into the zero-failure load interval. The socket and Python-thread series stayed bounded. Loopback microbenchmark rates are not production capacity estimates. The existing localhost:8900 process still returned HTTP 200 after the isolated server exited; protected-source and service evidence is in `reports/PHASE_3_PRESERVATION.json`.

Initial evidence is preserved as `reports/PHASE_3_SOAK_INITIAL.json` and `.csv`.

## Databases, preservation and sessions

Read-only inventory: `cryptoscope.ops.databases.inventory(Path.cwd())`. Initial inventory contained 19 database files: 13 working and six archival. After two batches of snapshots plus separate restore copies, the inventory contained **71 files: 69 WAL and two archived DELETE**. Counts are a point-in-time inventory, not a permanent invariant while the hourly backup worker runs. Both complete inventories are in `reports/PHASE_3_DATABASES_BEFORE.json` and `reports/PHASE_3_DATABASES_AFTER.json`. After the final-code backup worker restart, the final inventory contains 97 files; see `reports/PHASE_3_DATABASES_FINAL.json`. The earlier inventory remains preserved.

Working databases, all observed WAL after approved migration:

- `data/orders.db`
- `work/autotrader/autotrader.sqlite3`, `work/autotrader/paper.sqlite3`
- `work/research-agent/paper.sqlite3`, `work/research-agent/research.sqlite3`
- `work/crypto_candles.db`
- `work/runtime/crypto_candles.db`, `work/runtime/orchestrator_execution.db`
- `work/runtime/paper_execution.db`, `work/runtime/research.db`
- `work/runtime/trading.db`, `work/runtime/trading_journal.db`, `work/runtime/users.db`

The five user-approved DELETE-to-WAL migrations were the two autotrader databases, two research-agent databases and `work/crypto_candles.db`. All five report `logical_contents_unchanged=true`. The two DELETE archives are `work/backups/phase1-pre-migration-backup/autotrader.sqlite3` and `.../paper.sqlite3`; changing archival snapshots was not approved and was not done. No original database row was deleted or modified by this work. Evidence: `reports/PHASE_3_WAL_MIGRATION.json`.

`orchestrator_state.db` is a default filename in ExecutionBot but was absent from this workspace inventory; the fleet's explicitly configured `orchestrator_execution.db` exists. `trading_journal.db` exists. These names are not silently treated as the same file.

`busy_timeout` is a **per-connection** setting. The new shared connection factory sets 5000 ms for each read or write connection; research store, autotrader store, dashboard readers, ExecutionBot and JournalBot use it. AuthStore, CandleStore, PaperBroker, GovernorState, the archive reader and protected OrderManager already set explicit 5000 ms; shutdown checkpoint connections now do too. A `sqlite3.connect(timeout=3)` would initially configure 3000 ms, but a subsequent explicit `PRAGMA busy_timeout=5000` supersedes it for that connection. The 3-second `urlopen` in the protected governor is an HTTP timeout, not an SQLite setting. The inventory's own 5000-ms observation alone is not proof of other callers; the source paths above provide that evidence. Old diagnostic scripts are not production connection factories.

Five unexpired sessions were observed in users.db: row IDs **2, 3, 4, 5, 6**, all admin. Safe created/expiry timestamps are included in the inventory; authentication values and account responses are not published. Sessions and users were preserved.

The reported **131 rows** in `work/runtime/trading.db` are in `decision_journal`. That database also has five meta rows, four event rows, and zero positions, orders or PnL events at the observed snapshot. Journal row count is not an executed-trade count or a performance claim.

## Versioning and backups

All 13 existing working files still report `PRAGMA user_version=0`; they have legacy CREATE-IF-NOT-EXISTS schemas rather than a universal migration ledger. No production schema migration was run. New ExecutionBot startup performs an additive version-1 migration adding position provenance (`mode`, default UNKNOWN), retains legacy positions, and rejects unsupported future versions. Real disposable SQLite tests prove row preservation and fail-closed unknown provenance. This is a scoped migration, not a claim that all databases now have versioned schemas.

Actual backup batches (all originals and earlier copies retained):

1. `work/backups/phase3-[REDACTED]1106T114541-492516Z`: 13 consistent online SQLite backups and 13 separate restore checks, all integrity checks `ok` and logical restores equal.
2. `work/backups/phase3-[REDACTED]1107T084658-276668Z`: first observed hourly scheduled batch, same 13/13 outcome.

A third final-code batch also passed 13/13 backups and restores; its manifest is `reports/PHASE_3_BACKUP_FINAL.json`. Empty database inventories now produce `passed=false` and a failing one-shot CLI exit code, verified in isolation. The first hourly worker was stopped only after verifying its exact identity and replaced to load this final guard; current observed backup worker PID is **34480**. No trading process was stopped.

Commands: one-shot `python -B -m scripts.run_database_backups`; automatic `python -B -m scripts.run_database_backups --interval 3600`. The initial worker PID was **41444**; it was replaced by **34480** after the final guard was verified. The first batch precedes the approved WAL changes. Originals and older copies were never overwritten. Each database snapshot is consistent individually; this is not an atomic cross-database transaction or an off-machine disaster-recovery copy. Backup databases retain sensitive application state and stay in ignored local storage; only manifests with counts/schema/check outcomes are published.

Monitor new directories and `manifest.json` under `work/backups/phase3-*`. The worker is a running development process, not a registered Windows service and has not been proven to survive logout/reboot. It has no destructive retention policy. Later scheduled cycles must be observed separately; do not infer that they ran from the interval setting. Separately, a real two-cycle scheduler check at a 60-second interval on one disposable database captured values 1 then 2 in distinct preserved snapshots, with both restores passing. This proves repeated scheduling for that fixture, not a second hourly production batch. Evidence: `reports/PHASE_3_BACKUP_SCHEDULE.json`; retained fixture `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-msbpae5g`. Published manifests: `reports/PHASE_3_BACKUP_INITIAL.json`, `reports/PHASE_3_BACKUP_SCHEDULED.json`.

## Testnet and execution repairs

Approved authenticated requests: API-key-header `GET https://testnet.binance.vision/api/v3/historicalTrades?symbol=BTCUSDT&limit=1`, then the adapter's signed account GET (with its necessary read-only clock query). Both returned HTTP 200. Only status/success metadata was retained in `reports/PHASE_3_AUTH.json`; the account response was discarded. This establishes authentication on these requests, not trading permissions or order execution.

Implementation repairs in `cryptoscope/orchestrator/bots/execution_bot.py`, `cryptoscope/execution/binance_testnet.py` and `cryptoscope/security/halt_state.py`, all verified with explicit exchange stubs:

- Use a real STOP_LOSS request shape, without fabricated limit fields or a paper reference when protection fails. A confirmed entry stays tracked and the durable halt engages on a stop failure.
- Persist the exact deterministic client reference before sending an entry; a lost response or duplicate request cannot silently become a new entry on restart.
- Treat partial or invalid entry/exit results as reconciliation-required. Never label them complete or remove known exposure. Reject nonfinite fill numbers.
- Require confirmed stop cancellation and full close fill before removing a local position. Query a retained close reference rather than blindly resubmitting after a lost response. An already filled protective stop never causes a second market sell.
- Preserve actual exchange stop protection during watchdog emergency handling; changing a software stop value is not an exchange-side modification.
- Read protective order state at startup and every minute; mismatches halt without erasing exposure or auto-resuming.
- Have the fleet consume the dashboard's durable HALT_FLATTEN request. Dashboard response now distinguishes request acknowledgement from confirmed execution; completion is established by actual fills, not by receiving the button request. Plain HALT preserves known exposure and protective stops.

**Not yet proven or complete:** real lifecycle order IDs, automatic full accounting of partial fills and asset-denominated commissions, real rate-limit recovery, process-kill/restart under actual exchange exposure, cancellation/reconciliation of uncertain standalone entries, and a seven-day forward run. Ambiguous states are retained and halted for operator reconciliation. No real protective order is claimed to exist. New exchange behavior requires separate testnet-order approval and a bounded reviewed integration run before unattended trading. No live funds were accessed.

## Health, listing scope and spec

Read-only requests to the existing `http://127.0.0.1:8900` process returned:

- `/health`: HTTP 200, status healthy.
- `/ready`: HTTP 200, status ready; Binance, Coinbase, Kraken and CoinGecko states connected; FX available at that observation.
- `/api/market/tickers`: eight symbols.
- `/api/market/listings`: HTTP 200, 50 items on page 1, total 86, stale false, no error.

Evidence: `reports/PHASE_3_LOCAL_HEALTH.json`. The existing production dashboard was not restarted to load Phase 3 source; the new HTTP/telemetry implementation ran in the isolated soak. `/ready` is an informational response and currently returns 200 even when a dependency is degraded. It is not authorization or proof that trading is safe.

Eight tickers come from an explicit eight-symbol Binance feed configuration; Coinbase and Kraken cover three core symbols. These adapters currently poll public REST endpoints; old WebSocket endpoint labels in the status response do not prove WebSocket transport. It is not a dynamically expanded full trading universe. The prior five-listing observation is not reproduced now and its original cause cannot be established from the current response alone. Current listing pagination defaults to 50 and CoinGecko metadata requests the top 150 candidates. This is a bounded display list, not every listed coin or the Phase 5 point-in-time universe.

Source review found an extra static backend blacklist, static fallback universe, frontend blacklist and fallback cap. These were removed from activity filtering. Refreshed exchangeInfo must identify a Binance Spot USDT pair with status TRADING; unknown/expired exchange activity fails closed. Stablecoins that are active are not silently blacklisted in this display stage. Fallback rows require the same verified active set and do not invent missing market capitalization/ranks. Tests explicitly cover an active stablecoin, an inactive pair and unavailable universe. This source policy is independently stub-tested, but is not claimed to be loaded by the already-running production server. No layout, styling, branding or chart redesign was performed.

`README.md` and `[REDACTED]ERS_QUANT_ARCHITECTURE.md` now agree with executable gate definitions: explicit LIVE flag; legacy exchange settings present; default 28 forward days/100 trades/positive net PnL/drawdown at most 15%/DSR at least 0.95; admin reauthentication within 300 seconds; exact `ENABLE LIVE TRADING` confirmation (after surrounding whitespace removal). Authentication uses `work/runtime/users.db`.

Existing protected-governor limitations are disclosed instead of changed: Gate 2 does not independently establish withdrawal permissions; omitted DSR defaults to the configured threshold; aggregate-only callers can omit timestamp provenance; the old docstring's DSR 0.80 is stale. The durable halt and pre-trade controls are additional execution checks, not a substitute list of activation gates. `cryptoscope/execution/governor.py` and `docs/MASTER_PROMPT.md` remain unchanged.

## Remaining boundary

Phase 3 is not a blanket trading-readiness PASS. Both soak outcomes are retained, and the repaired run remains REVIEW under its frozen memory criterion. Real lifecycle tests still need a bounded reviewed plan and separate order approval. Partial-fill/commission accounting and uncertain-entry reconciliation must be completed before an unattended run. No seven-day or Phase 4 job may be inferred from authentication success. Phase 1 still blocks Phase 4; the Phase 2 historical integrity result does not establish an edge. **Do not trade live.**

Published artifacts are sanitized with the existing report scanner. Some benign identifiers or numeric measurements may be withheld by the strict matcher; untouched original local outputs are retained at their documented private paths. Null/redacted fields are not reconstructed as performance evidence.
