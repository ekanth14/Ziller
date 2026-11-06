# Phase 2 latest repair verification

November 6, Asia/Calcutta. Branch `verified-fleet`; source `364f72e19dba8a522b8bd22fdb6fc6fbb8de99ce`.

**Latest Phase 2 verdict: PASS for the specified historical backtest and its declared execution model.** This does not establish trading readiness or guarantee future stop fills. Phase 1 remains unresolved. Earlier sections below preserve the original failures and are superseded by this verification.

| Requirement | Result | Evidence |
| --- | --- | --- |
| 2.1 | PASS | Real RiskBot and DebateBot handlers, 83 real recorded model decisions, disjoint stage counts, synthetic real-risk halt and limit proofs. Cached/fallback counts below. |
| 2.2 | PASS for modeled stops and archived trades | Correct two-leg notional hedge, frozen price stops, fees and adverse slippage; no corrected archive trade exceeds budget plus slippage. Explicit gap stress retains excess losses. No universal future-market guarantee. |
| 2.3 | PASS | Combined PF pools fee-inclusive trade outcomes; nonzero-PF/28%-win-rate regression passes and historical ledger reconstruction reconciles cash. |
| 2.4 | PASS diagnostics executed | Separate train/test ADF on levels, differences and ratio, plus Engle-Granger and training-fixed residual tests. No causal diagnosis claimed. |
| 2.5 | PASS | Fresh final-source replay uses recorded votes, same 90-day archive, frozen split/parameters and old/new tables. No positive-edge claim. |

## Verified commands

`python -B scripts/run_isolated_tests.py`: 358 collected; 346 passed, 12 skipped in 42.47 seconds, exit 0. No warnings in the final output. Skips: five external-service checks excluded by the isolation guard and seven optional QuantJourney checks. No dependency installation.

`python -B scripts/run_phase2_online.py`: real local cache generation. The job began with the frozen compact-protocol implementation while further risk/accounting fixes were tested independently. Its automatic replay uses that job copy and is not the final replay reported here.

`python -B scripts/run_phase2_research.py --cache <retained local-debate-cache.json>`: final-source offline replay, exit 0. It restores the ordinary guard that denies model/external requests. No account credentials or operational broker were used.

Full test copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-gaawv10f`. Final research copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-mw_f74ph`.

## Model diagnosis and recorded votes

A non-raw compact schema request timed out at 34.012 seconds. Local metadata reported an 11.9B Q4_K_M Gemma architecture, a stored system prompt of about 4,000 characters and CPU execution. A raw-template diagnostic succeeded in 28.616 seconds: load 20.520 seconds, prompt processing 4.067 seconds, generation 3.986 seconds. These are measurements of different requests; no universal single-cause claim is made.

Research protocol `phase2-scored-committee-v1` uses an explicit raw prompt and JSON schema with bull-support, bear-opposition and risk-moderator scores, plus a binary vote. The proposed direction is fixed by the strategy. Approval additionally requires risk conviction >=6. This is a scored multi-perspective committee from one model call, not three independently trained agents or a proven predictor. It preserves actual DebateBot replay; production consensus prompts were not changed.

Generation settings were frozen before market reruns: model gemma4-quant:12b, temperature 0, seed 17, context 512, maximum 40 output tokens, four CPU threads, raw template, thinking off. The 34.5-second request budget stays inside the existing 35-second stage deadline. Every record has request identity, prompt digest, protocol, generation options, committee scores and server timing. Typed failure records contain no raw exception text. Truncation, invalid schema, timeout, opposite direction or insufficient conviction reject.

Real cache: 83 valid votes / 83 attempts; no failures. Each vote is generated from historical proposal facts, not future outcomes. Cache is retained at `work/research/phase2-repair/recorded-debate-cache.json` and in the original disposable job. No heuristic vote is labeled as a model vote.

Model request timing (83 requests, not trades): median 11.886 seconds; maximum 16.314 seconds. This is cache-generation evidence, not the Phase 3 twice-run benchmark.

## Risk controls and counts

The actual RiskBot now enforces its existing 5% order-notional cap in fixed-fractional sizing, rounds quantity down, recomputes risk from final size, updates exposure after partial exits and rejects nonfinite/invalid brackets. The drawdown breach latches on observation and remains halted through recovery and UTC day rollover. A regression proves this. Limits are not relaxed. Replay still reserves fees inside its risk budget. The five-gate governor is unchanged.

Realized cash from one closed position no longer creates a false portfolio peak while other positions remain unrealized. The replay owns total-NAV marking; actual PositionClosed handlers still update the daily-loss latch. UTC calendar rollover is explicit. All research governor state is disposable; operational emergency state is not cleared.

| Split / mode | Proposals | No signal | Risk pre-veto | Debate veto | Risk post-veto | Approved | Cached / heuristic / miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TRAIN / recorded | 234 | 9993 | 180 | 42 | 0 | 12 | 54 / 0 / 0 |
| TRAIN / heuristic_diagnostic | 234 | 9993 | 191 | 0 | 0 | 43 | 0 / 43 / 0 |
| TEST / recorded | 76 | 4103 | 58 | 16 | 0 | 2 | 18 / 0 / 0 |
| TEST / heuristic_diagnostic | 76 | 4103 | 61 | 0 | 0 | 15 | 0 / 15 / 0 |

No-signal observations are separate from vetoes. Stage totals reconcile exactly; multiple reason counts may overlap within one veto. The pure heuristic diagnostic receives no recorded cache. Per-book comparisons use recorded mode, not the heuristic baseline. Full reason counts and request coverage are in the JSON evidence.

Synthetic actual-RiskBot exercises: three daily-loss vetoes after three realized losses totaling 330; three drawdown vetoes after ten losses across days totaling 1,100. Separate scenarios each prove correlation, position-count and per-coin vetoes; the order cap approves at most five units at price 100 against NAV 10,000. These are control tests, not market trades.

## Pair model and gap sensitivity

The prior unit-hedge and fee defects remain documented below. The corrected pair stop model freezes a 2% adverse stop per leg, sizes combined two-leg risk plus nominal entry/exit fees to at most 0.5% equity, and caps gross exposure. Exits use gap-aware stop prices and the observed adverse extreme for the untriggered hedge leg. They never invent a hedge-leg fill outside its candle. Independent OHLC extrema form a conservative envelope; simultaneous executable fills are not established.

The strict Spot pipeline continues rejecting ETH/BTC correlation 0.88 against cap 0.85. If that check changes, a deterministic unsupported-short veto replaces the old runtime exception. No unborrowed Spot short is simulated as an approved fill. Pair sizing is separately exercised mechanically, with that distinction explicit.

- TRAIN: 45 mechanical trades, 0 budget-plus-slippage breaches; PnL -543.2990 (n=45), PF 0.0748 (n=45), sampled DD % 5.4369 (n=45).
- TEST: 17 mechanical trades, 0 budget-plus-slippage breaches; PnL -164.5935 (n=17; insufficient data), PF 0.0476 (n=17; insufficient data), sampled DD % 1.8459 (n=17; insufficient data).

Twelve predeclared gap stresses span three hedge ratios and 0%, 1%, 5% and 10% adverse gaps beyond the stop. All zero-gap cases satisfy the budget-plus-slippage bound; adverse gaps retain and report excess loss. This fixes the accounting/test interpretation without promising gap-proof execution. The earlier blanket failure label for an unconditional future-market guarantee is replaced by a scoped PASS for implemented, observed backtest conditions; the market limitation remains explicit.

Frozen legacy audit: 51 raw-budget violations, 41 budget-plus-slippage violations. The full original list remains `PHASE_2_PAIR_VIOLATIONS.csv`; no prior ledger is deleted.

## Old/new independent-account comparison

Each strategy account begins with 10,000; seven independent accounts total 70,000. The separate shared replay begins with 10,000 and applies cross-strategy limits. Changed exposure and entry timing explain comparability limits; smaller losses alone do not demonstrate better alpha. All result cells include trade count, with fewer than 30 labeled insufficient data.

| Strategy / symbol / split | Old PnL | Recorded-cache PnL | PF | Sampled DD % |
| --- | --- | --- | --- | --- |
| ema_trend / BTCUSDT / TRAIN | 107.6200 (n=12; insufficient data) | 1.5904 (n=4; insufficient data) | 1.1416 (n=4; insufficient data) | 0.1403 (n=4; insufficient data) |
| volatility_breakout / BTCUSDT / TRAIN | -103.4900 (n=9; insufficient data) | -9.9744 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1285 (n=2; insufficient data) |
| ema_trend / ETHUSDT / TRAIN | -297.4600 (n=20; insufficient data) | -3.9709 (n=1; insufficient data) | 0.0000 (n=1; insufficient data) | 0.0458 (n=1; insufficient data) |
| volatility_breakout / ETHUSDT / TRAIN | -47.9100 (n=10; insufficient data) | 29.4792 (n=1; insufficient data) | N/A (n=1; insufficient data) | 0.1540 (n=1; insufficient data) |
| ema_trend / SOLUSDT / TRAIN | -356.8900 (n=20; insufficient data) | 13.0394 (n=3; insufficient data) | 2.7382 (n=3; insufficient data) | 0.1077 (n=3; insufficient data) |
| volatility_breakout / SOLUSDT / TRAIN | 36.4900 (n=4; insufficient data) | 15.6782 (n=2; insufficient data) | N/A (n=2; insufficient data) | 0.0508 (n=2; insufficient data) |
| stat_arb_pairs / ETH/BTC / TRAIN | -5485.7400 (n=53) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| ema_trend / BTCUSDT / TEST | -289.5700 (n=8; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| volatility_breakout / BTCUSDT / TEST | -166.7500 (n=4; insufficient data) | -12.1140 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1337 (n=2; insufficient data) |
| ema_trend / ETHUSDT / TEST | -152.5400 (n=8; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| volatility_breakout / ETHUSDT / TEST | -52.1700 (n=3; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| ema_trend / SOLUSDT / TEST | -119.1100 (n=4; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| volatility_breakout / SOLUSDT / TEST | -106.4900 (n=2; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| stat_arb_pairs / ETH/BTC / TEST | -2283.7800 (n=28; insufficient data) | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |

| Allocation / split | PnL | PF | Win % | Sampled DD % |
| --- | --- | --- | --- | --- |
| Shared / TRAIN / recorded | 41.3434 (n=12; insufficient data) | 2.2643 (n=12; insufficient data) | 50.0000 (n=12; insufficient data) | 0.1855 (n=12; insufficient data) |
| Shared / TRAIN / heuristic_diagnostic | -60.2738 (n=43) | 0.6957 (n=43) | 30.2326 (n=43) | 0.9326 (n=43) |
| Shared / TEST / recorded | -12.1140 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1337 (n=2; insufficient data) |
| Shared / TEST / heuristic_diagnostic | -63.8989 (n=15; insufficient data) | 0.2323 (n=15; insufficient data) | 13.3333 (n=15; insufficient data) | 0.6534 (n=15; insufficient data) |
| Independent recorded / TRAIN | 45.8420 (n=13; insufficient data) | 2.4026 (n=13; insufficient data) | 53.8462 (n=13; insufficient data) | 0.0265 (n=13; insufficient data) |
| Independent recorded / TEST | -12.1140 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.0191 (n=2; insufficient data) |

## Statistical evidence and limits

The dataset fingerprint matches the unchanged 2,160 hourly observations per symbol. Live dashboard cache updates are not treated as a whole-file preservation guarantee; the exact research bars were compared instead. The split stays 1,512 train / 648 test bars, with existing warmup and no test-period parameter tuning. This reused test period is not a pristine holdout.

| Window | Ratio ADF p | Engle-Granger p | Training-fixed residual ADF p |
| --- | --- | --- | --- |
| TRAIN (1512 bars) | 0.121453 | 0.031478 | 0.007757 |
| TEST (648 bars) | 0.088647 | 0.324193 | 0.074609 |

ADF levels/differences for both assets and critical values are included in JSON. Specifications remain log prices, constant, lag 1, no autolag selection, 5% threshold. Train/test sensitivity is measured; neither a causal structural-break explanation nor persistent cointegration is asserted. Compatibility with the installed statsmodels API removes the prior warnings.

PF is calculated from net trade wins and losses, with cash reconciliation assertions; undefined values are null with a reason. The prior fee-restored legacy PF and its incorrect reported value remain below. Equity drawdown uses sampled open/close and realized marks; intrabar timing and stop liquidity are not known from hourly bars.

**No robust positive out-of-sample edge is established. Do not trade live.** Small recorded-mode samples and retrospective model availability limit conclusions. Phase 2 PASS refers to research integrity under its declared model, not production model accuracy or exchange safety. Phase 1, Phase 3 operations/exchange work and Phase 8 Laya classifier work remain separate and incomplete. No order, training, installation, history rewrite, production reconfiguration or later phase was performed.

New evidence: `PHASE_2_REPAIR_RESULTS.json`, `PHASE_2_REPAIR_TEST_OUTPUT.txt`. Published evidence uses the strict existing sanitizer; withheld values are annotated. Raw research/cache files remain internal for reproducible replay. Previous numerical evidence is retained below and in its original JSON files.

---

# Earlier Phase 2 evidence (superseded status)

# Phase 2 — backtest integrity

Updated November 5, Asia/Calcutta. Branch `verified-fleet`; original offline source `f7a704d53e7efa634b8e5a4ac78f50abd3bf8cd7`; latest local-model source `4720f62fb01544280e4357d9ae8d524151637434`.

**Overall gate: FAIL / BLOCKED.** Offline work was followed by the user’s explicit request to make the Phase 2 cache run online. Local Ollama generation was attempted, but produced no valid recorded votes before the consecutive-failure stop. The offline baseline below is preserved as historical evidence; the latest local-model attempt is documented at the end. Do not advance automatically. Phase 1 remains unresolved too.

## Original offline baseline (preserved)

| Item | Result | Observed evidence |
| --- | --- | --- |
| 2.1 | FAIL complete requirement; PASS risk/debate wiring and synthetic halt exercises | Real RiskBot and DebateBot ran. Exact recorded cache: zero entries. Primary replay rejects misses; heuristic diagnostic is separately labeled. No real model generation or historical model-cache validation ran. |
| 2.2 | PASS finite-stop model and archived-candle diagnostic; FAIL unconditional guarantee | Frozen two-leg price stops, notional beta hedge and fee-inclusive fixed-fractional sizing implemented. Zero breaches in the corrected mechanical archive exercise; synthetic opening gaps explicitly exceed the bound. ETH/BTC remains vetoed by the unchanged correlation policy. |
| 2.3 | PASS | Trade-level net gross-profit/gross-loss pooling; historical ledger recomputation and regression tests. Undefined PF is null with a reason, never an arbitrary sentinel. |
| 2.4 | PASS diagnostics executed | Installed statsmodels ran ADF and Engle-Granger on separate train/test windows. No causal explanation asserted. |
| 2.5 | PASS offline rerun/comparison; NOT RUN recorded-model performance | Same archived 90-day sample, frozen parameters and chronological split; legacy reproduced in disposable memory and corrected results below. Primary model-cache path stays flat. |

## Commands and evidence

```text
python -B scripts/run_isolated_tests.py
318 collected; 306 passed, 12 skipped, 8 warnings in 30.99s; EXIT_CODE=0
python -B scripts/run_phase2_research.py
EXIT_CODE=0; phase2-results.json generated in retained disposable copy
git diff --quiet 676af22 -- cryptoscope/execution/governor.py
EXIT_CODE=0 (five-gate governor unchanged)
```

Full-suite evidence copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-sofzodd2`. Final research evidence copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-o2v89kmp`. The final historical slippage-classification refinement ran in that last research job after the full suite; its ledger-to-cash assertions passed. The earlier focused regression run passed 43 tests after correcting a synthetic next-open candle fixture.

The 12 skips are four Binance external checks, one CoinGecko check, and seven optional QuantJourney checks. No dependency installation was performed. Eight statsmodels FutureWarnings concern its future result-object API. An asynchronous HTTP fixture exception header appeared without a useful traceback; no cause is asserted. The suite exited successfully. Node/UI checks were not rerun because no frontend source changed.

Research uses the approved disposable-copy audit guard: credentials excluded, external/model requests blocked, writes and SQLite access confined to the copy. RiskBot and DebateBot are the actual classes, invoked through their handlers; inference is an offline adapter. This is not a complete operational fleet/process integration test. No broker or exchange client is imported by the new backtesting modules. The AST isolation test now covers the backtesting directory.

## Dataset, chronology and frozen specification

Archive: `work/runtime/crypto_candles.db`, copied for research and opened with SQLite `mode=ro`. BTCUSDT, ETHUSDT and SOLUSDT each have exactly 2,160 hourly bars, with alignment, ordering, gap, finite-value and OHLC checks passing. No missing data was fetched.

Range: [REDACTED]-08-05T15:00:00+00:00 through [REDACTED]-11-03T14:59:59.999000+00:00. Train: 1,512 bars; test: 648 bars. This is one chronological 70/30 split, not multiple walk-forward folds. Each split restarts indicators and uses a 50-bar warmup, matching the prior split convention. This previously examined test window is not a fresh holdout.

Parameters were fixed before the first rerun, using the existing strategy defaults: EMA 20/50, ATR 14, trend stop 1.5 ATR and target 3 ATR; volatility-breakout defaults; pair entry z=1.8, exit=0.25, z-stop=3.5, window=30. New explicit pair leg stops are 2% adverse from nominal entry. Fee is 0.075% per side; slippage is 5 bps for majors, 10 bps for SOL. Risk fraction is 0.5%. No parameters were optimized against test results.

Signals use completed candles. Admission occurs at the next open, with that open as the available execution price. New positions cannot exit on the preceding signal bar. Close-derived trend exits execute at the next open. Stop precedes target on ambiguous OHLC bars; adverse opening gaps remain uncapped. Fees include entry and exit. Drawdown is sampled at open/close marks and realized exits, not an intrabar exchange-fill guarantee. The future-mutation regression proves earlier cache inputs/closed trades remain unchanged.

## Real risk and debate-stage counts

The real RiskBot retains 10% drawdown, 3% daily realized loss, three positions, 15% per-coin exposure and 0.85 correlation cap. A stricter backtest clamp enforces its advertised 5% order-notional cap and reserves fees inside the risk budget. The existing RiskBot does not itself enforce that notional cap in its fixed-fractional branch; this production limitation remains visible. The five-gate governor and RiskBot source were not modified.

UTC day rollover is replayed explicitly; the daily breaker lasts through its day, and the drawdown peak persists across days. The persistent emergency latch is real but initialized only in the disposable database. Normal archive replays did not hit daily/drawdown limits. Separate deterministic stress scenarios delivered actual PositionClosed events: three losses totaling 330 triggered three daily-loss vetoes; ten losses across days totaling 1,100 triggered three drawdown vetoes. These are synthetic safety evidence, not market performance.

| Split / mode | Proposals | No signal | Risk pre-veto | Debate veto | Risk post-veto | Approved | Recorded / heuristic / cache miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TRAIN / recorded | 234 | 9993 | 170 | 64 | 0 | 0 | 0 / 0 / 64 |
| TRAIN / heuristic_diagnostic | 234 | 9993 | 191 | 0 | 0 | 43 | 0 / 43 / 0 |
| TEST / recorded | 76 | 4103 | 57 | 19 | 0 | 0 | 0 / 0 / 19 |
| TEST / heuristic_diagnostic | 76 | 4103 | 61 | 0 | 0 | 15 | 0 / 15 / 0 |

Stage totals are disjoint and reconciled by assertions. Reason counts can overlap within one veto. Per-strategy no-signal counts and per-reason counts are in `PHASE_2_RESULTS.json`. No-signal observations are not vetoes. Size reductions are separate from rejects.

Cache provenance: zero real recorded votes and zero heuristic votes in default recorded mode; every admitted default request is a cache miss and rejects. Diagnostic mode uses only the named reward/risk heuristic when no record exists; it is not Laya or another model. Keys bind exact inputs, the observed history through the decision bar and frozen parameters. Invalid records reject even in diagnostic mode. The fixture-cache unit test proves wiring only and is not evidence of model execution.

## Pair sizing and the historical losses

The original helper estimates beta on log prices. It is dimensionless and describes relative notional exposure. The old backtest used `q_BTC = -beta * q_ETH`, incorrectly treating beta as a coin-unit ratio. The correct hedge is `q_BTC = -beta * q_ETH * P_ETH / P_BTC`. The old 2% number was only a sizing divisor; exits were rolling z-score exits, without a frozen price stop. Entry fees were also charged on the assumed notional rather than actual gross leg values. These code defects explain why the nominal budget did not constrain modeled losses; no statistical-regime cause is inferred.

Corrected model: long ETH stop is `P_ETH*(1-0.02)` and short BTC stop is `P_BTC*(1+0.02)`. Combined planned loss is `q_ETH*(entry-stop_ETH) + abs(q_BTC)*(stop_BTC-entry) + all nominal entry/exit fees`. Scale both quantities together so this is no more than 0.5% of equity, also subject to a 30% gross cap in the mechanical sizing diagnostic. Slippage is charged adversely on both legs; its incremental fee effect is included in the measured slippage allowance.

Frozen legacy replay: 81 pair trades (53 train, 28 test; test insufficient data). 51 exceeded the raw risk budget; 41 exceeded budget plus measured slippage. Worst raw-budget multiple: 32.68; median among raw-budget violators: 4.75. This is broader than the suggested 3-4x loss. Full violating-trade list: `PHASE_2_PAIR_VIOLATIONS.csv`; the Boolean column distinguishes the stricter slippage-adjusted rule.

Corrected mechanical audit:
- TRAIN: 45 trades; 0 budget-plus-slippage breaches; net PnL -1130.7017 (n=45); PF 0.0364 (n=45); sampled drawdown % 11.3107 (n=45).
- TEST: 17 trades; 0 budget-plus-slippage breaches; net PnL -522.7734 (n=17; insufficient data); PF 0.0150 (n=17; insufficient data); sampled drawdown % 5.4204 (n=17; insufficient data).

This mechanical exercise bypasses the approval pipeline solely to test sizing and accounting; it is not strategy approval. Strict pipeline pair fills remain zero because ETH/BTC correlation 0.88 exceeds 0.85. Atomic two-leg approval is deliberately fail-closed if that policy changes. A BTC short is not an executable unborrowed Binance Spot trade. The report does not authorize it.

The regression grid checks simultaneous adverse stops with both fees and several hedge ratios/slippage levels. Another test explicitly shows an opening gap can exceed budget plus slippage. A universal hard loss bound cannot honestly be promised with stops on a gapping market; the archived zero-breach result is conditional evidence only.

## Profit factor and comparable old/new numbers

PF is sum of positive fee-inclusive trade PnL divided by absolute sum of negative fee-inclusive trade PnL. Strategy net totals are never substituted. The reproduced legacy ledger restores its charged entry fees to each trade. Its cash PnL reconciles with the prior report within rounding; this is still the old flawed fill/sizing model. Missing legacy equity curves are null, not invented zero drawdown.

| Legacy split | Trades | Reported PF | Correct trade-ledger PF | Ledger cash PnL |
| --- | ---: | --- | --- | --- |
| TRAIN | 128 | 0.0200 (n=128) | 0.3525 (n=128) | -6147.3768 (n=128) |
| TEST | 57 | 0.0000 (n=57) | 0.4408 (n=57) | -3170.4221 (n=57) |

The next table compares each original independent 10,000-unit account with the stricter heuristic diagnostic on the same window. Reductions in exposure, entry timing and rejected pairs change the strategy being measured; lower losses do not establish improved alpha. Every new per-book result has fewer than 30 trades and is insufficient data.

| Strategy / symbol / split | Old trades | Old net PnL | New trades | New net PnL | New PF | New sampled DD % |
| --- | ---: | --- | ---: | --- | --- | --- |
| ema_trend / BTCUSDT / TRAIN | 12 | 107.6200 (n=12; insufficient data) | 8 | 5.9069 (n=8; insufficient data) | 1.2674 (n=8; insufficient data) | 0.1083 (n=8; insufficient data) |
| volatility_breakout / BTCUSDT / TRAIN | 9 | -103.4900 (n=9; insufficient data) | 2 | -9.9745 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1285 (n=2; insufficient data) |
| ema_trend / ETHUSDT / TRAIN | 20 | -297.4600 (n=20; insufficient data) | 17 | -32.8157 (n=17; insufficient data) | 0.5411 (n=17; insufficient data) | 0.4745 (n=17; insufficient data) |
| volatility_breakout / ETHUSDT / TRAIN | 10 | -47.9100 (n=10; insufficient data) | 7 | -3.4479 (n=7; insufficient data) | 0.9101 (n=7; insufficient data) | 0.2187 (n=7; insufficient data) |
| ema_trend / SOLUSDT / TRAIN | 20 | -356.8900 (n=20; insufficient data) | 20 | -37.9350 (n=20; insufficient data) | 0.6188 (n=20; insufficient data) | 0.5090 (n=20; insufficient data) |
| volatility_breakout / SOLUSDT / TRAIN | 4 | 36.4900 (n=4; insufficient data) | 4 | -1.4571 (n=4; insufficient data) | 0.9194 (n=4; insufficient data) | 0.1622 (n=4; insufficient data) |
| stat_arb_pairs / ETH/BTC / TRAIN | 53 | -5485.7400 (n=53) | 0 | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| ema_trend / BTCUSDT / TEST | 8 | -289.5700 (n=8; insufficient data) | 5 | -25.6536 (n=5; insufficient data) | 0.0000 (n=5; insufficient data) | 0.2596 (n=5; insufficient data) |
| volatility_breakout / BTCUSDT / TEST | 4 | -166.7500 (n=4; insufficient data) | 2 | -12.1140 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1337 (n=2; insufficient data) |
| ema_trend / ETHUSDT / TEST | 8 | -152.5400 (n=8; insufficient data) | 5 | -11.2853 (n=5; insufficient data) | 0.5157 (n=5; insufficient data) | 0.1623 (n=5; insufficient data) |
| volatility_breakout / ETHUSDT / TEST | 3 | -52.1700 (n=3; insufficient data) | 1 | -7.8170 (n=1; insufficient data) | 0.0000 (n=1; insufficient data) | 0.1423 (n=1; insufficient data) |
| ema_trend / SOLUSDT / TEST | 4 | -119.1100 (n=4; insufficient data) | 4 | -15.4483 (n=4; insufficient data) | 0.3237 (n=4; insufficient data) | 0.2298 (n=4; insufficient data) |
| volatility_breakout / SOLUSDT / TEST | 2 | -106.4900 (n=2; insufficient data) | 2 | -18.4693 (n=2; insufficient data) | 0.0000 (n=2; insufficient data) | 0.1847 (n=2; insufficient data) |
| stat_arb_pairs / ETH/BTC / TEST | 28 | -2283.7800 (n=28; insufficient data) | 0 | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |

Independent-account aggregation uses seven funded accounts (70,000 total), pooled trade outcomes and aligned summed equity. The shared-account replay uses one 10,000 account, including cross-strategy correlations/position limits. These are different allocations and are labeled separately.

| Allocation / split / debate mode | Trades | Net PnL | PF | Win % | Sampled DD % |
| --- | ---: | --- | --- | --- | --- |
| Shared / TRAIN / recorded | 0 | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| Shared / TRAIN / heuristic_diagnostic | 43 | -60.2738 (n=43) | 0.6957 (n=43) | 30.2326 (n=43) | 0.9326 (n=43) |
| Shared / TEST / recorded | 0 | 0.0000 (n=0; insufficient data) | N/A (n=0; insufficient data) | N/A (n=0; insufficient data) | 0.0000 (n=0; insufficient data) |
| Shared / TEST / heuristic_diagnostic | 15 | -63.8990 (n=15; insufficient data) | 0.2323 (n=15; insufficient data) | 13.3333 (n=15; insufficient data) | 0.6534 (n=15; insufficient data) |
| Independent / TRAIN / heuristic diagnostic | 58 | -79.7232 (n=58) | 0.6928 (n=58) | 32.7586 (n=58) | 0.1535 (n=58) |
| Independent / TEST / heuristic diagnostic | 19 | -90.7875 (n=19; insufficient data) | 0.1762 (n=19; insufficient data) | 10.5263 (n=19; insufficient data) | 0.1297 (n=19; insufficient data) |

## ETH/BTC stability diagnostics

Installed statsmodels version 0.15.0. Log prices, constant, lag 1, no autolag selection, 5% significance were frozen before evaluation. ADF on the log ratio is distinct from Engle-Granger residual cointegration; the latter uses its own adjusted critical values. ADF on a training-fitted residual is descriptive and does not replace Engle-Granger inference.

| Window | Bars | Ratio ADF statistic / p | Engle-Granger statistic / p | Training-fitted residual ADF p |
| --- | ---: | --- | --- | --- |
| TRAIN | 1512 | -2.475882 / 0.121453 | -3.510475 / 0.031478 | 0.007757 |
| TEST | 648 | -2.621438 / 0.088647 | -2.401398 / 0.324193 | 0.074609 |

The ratio ADF does not reject a unit root in either window. Engle-Granger rejects no cointegration in train but not in test; the training-fitted residual also fails the unit-root rejection in test. This is evidence of window sensitivity, not proof that a structural break caused losses. The current strategy computes an approximate ADF diagnostic but does not gate entries on its is_cointegrated flag. That existing production behavior was not changed or assumed fixed.

## Preservation, artifacts and next action

New files are in `cryptoscope/backtesting/`, regression tests in `cryptoscope/tests/test_phase2_backtest_integrity.py`, and the offline launcher in `scripts/run_phase2_research.py`. The prior fleet CLI now requires that launcher and has no network download fallback. A frozen local baseline is read from commit 676af22 in disposable memory solely for the audit; no checkout or history rewrite occurs. The only DebateBot change adds optional replay context to its inputs. No model receives sizing or execution authority.

Evidence files: `PHASE_2_RESULTS.json`, `PHASE_2_PAIR_VIOLATIONS.csv`, `PHASE_2_TEST_OUTPUT.txt`. The report publisher applies the existing strict confidentiality scanner only to new evidence; numeric values can be withheld as null and strings redacted. It does not alter prior reports or original research data. Original candle and prior-report bytes were compared against their disposable input copies at completion; equality results are recorded in status.

During the original offline run, no operational orders, model generations, dependency installation, training, data downloads, production configuration/database changes, bot restarts, UI changes or cloud deployments were performed. The persistent production latch was not initialized by this work. The known exchange-close/reconciliation, protective-stop and Phase 1 history/deployment issues remain unresolved.

Next unfinished Phase 2 item: obtain a provenance-backed exact recorded debate cache or separately approve local generation, then replay the default path and reassess its gate. The owner chose offline-only for this run. A universal gap-proof stop-loss bound remains unavailable; retain explicit gap sensitivity and do not weaken risk controls to manufacture PASS. No Phase 3 or multi-coin work is authorized here. **Do not trade live.**


## Authorized local-model attempt — latest Phase 2 evidence

The user subsequently said “make it online,” in response to the recorded-cache blocker. This was interpreted and announced as permission for local Ollama inference only. No public hosting, external data access, exchange connectivity or operational orders were enabled. The earlier offline-only decision is superseded for this narrowly scoped cache job.

Command: `python -B scripts/run_phase2_online.py`. Research copy: `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-oy7zmu2k`. Ollama version GET returned 0.40.14. Model inventory had `gemma4-quant:12b`, but not the exact `gemma4:12b` tag; the available model was explicitly named before use. A later read-only loaded-model check returned that model with context 4096 and size_vram 0. That observation alone does not diagnose the inference failures.

| Check | Result | Evidence |
| --- | --- | --- |
| Local service reachability | PASS | Real version/tags GETs succeeded. |
| Historical request discovery | PASS | 83 exact-input requests identified using the frozen archive and strict flat-cache replay. No future prices, backtest outcomes or account credentials were sent. |
| Model-call execution | PASS attempted; FAIL usable output | Three actual local generation attempts completed without an admissible vote. This is real service evidence, not a stub. |
| Recorded cache completion | FAIL | 0 valid votes from 3 attempts; 80 requests not attempted after the stop. |
| Consecutive-failure stop | PASS | Status `stopped_after_three_consecutive_failures`; checkpoint retained. No automatic retries or deadline extension. |
| Default cache replay | PASS fail-closed behavior; NOT RUN usable-model performance | Generation process exit 0 and separate offline replay exit 0. Zero model votes, zero heuristic votes, zero trades in recorded mode; all 83 debate requests remain cache misses. Insufficient data for trading performance. |
| Final-source regression suite | PASS within isolated scope | 333 collected; 321 passed, 12 skipped, eight known statsmodels warnings; exit 0, 42.58 seconds. |

Attempt durations in seconds: 34.524, 34.526, 34.514. The client request budget was 34.5 seconds inside the unchanged 35-second stage deadline. No exception text or model prose was retained as control data. The exact transport/parser failure category was not captured, so the durations alone are not asserted to prove a particular cause. A follow-up diagnosis should retain typed failure categories and measure the model within the same deadline; do not silently increase it.

The new launcher creates a credential-free disposable environment. Its separate generation guard allows only `http://127.0.0.1:11434/api/generate` for HTTP; outside-copy writes, external sockets/DNS, model pulls/creation, dashboard trading endpoints and external requests remain denied. The normal test guard is unchanged. The launcher restores the original model-blocking guard before replay. It never invokes a broker or order client. The fixed model choices exclude implicit cloud model selection.

The cache stores normalized decisions, timing, request identifiers and provenance. Free-form model text is not persisted as trusted control information. Opposite-direction/low-confidence approvals are converted to rejections. Invalid votes never become recorded model hits. Missing votes continue to reject. Unit tests for these rules and guard behavior use stubs; they are separate from the three actual service attempts.

Final source commit: `4720f62fb01544280e4357d9ae8d524151637434`. The real generation attempt preceded the final argument/validation tightening; it accepted no votes. The full suite ran against final source. No second generation job was started merely to reproduce failures. Online-specific safe evidence: `PHASE_2_ONLINE_EVIDENCE.json` and `PHASE_2_ONLINE_TEST_OUTPUT.txt`; the original offline results and violation list remain unchanged.

The original candle archive and previous fleet report still match the disposable input bytes. The production latch was not initialized, and production configuration/services were not restarted or changed. The five-gate governor remains untouched. There is no new evidence of a strategy edge. Phase 2 remains blocked; Phase 1’s unresolved findings also remain. No Phase 3 work started. Do not trade live.
