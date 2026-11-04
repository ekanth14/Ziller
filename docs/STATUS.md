# ZILLERS development status

Updated: 2026-11-04 (Asia/Calcutta).

## Authoritative instructions and permitted scope

- `docs/MASTER_PROMPT.md` contains the exact UTF-8 bytes of the master-prompt body from `C:\Users\Ekanth's laptop\Downloads\ZILLERS_CODEX_FIRST_RUN.txt`, preserving its line endings. The marker lines and cover note are excluded.
- The source file's first-run cover note authorizes Phase 0 and Phase 1 only, in order. Stop after Phase 1. No Phase 2 or later work, downloads, training, soak runs, or trading runs are authorized.
- Actual repository: `C:\Users\Ekanth's laptop\Desktop\my projects\zien-crypto`. Names such as `zien-quant` in the master prompt refer to this same existing repository.
- The master prompt defines Part B as multi-coin work (Phases 4-7), and Part C as Laya classifier work (Phase 8). These definitions supersede earlier conversational labels.
- The user approved fast-forwarding `verified-fleet` to `laya-decision`. This completed without conflict; both branches pointed to `75d915e` before Phase 0 work. No existing commit was rewritten.

## Current Git evidence

| Check | Fresh observation |
| --- | --- |
| Current branch | `verified-fleet` |
| HEAD / last commit | `75d915e3f07ae209ce4b5691977c5fdd18dd8be9` |
| Last commit subject | `chore(research): create requirements-research.txt for heavy ML dependencies per Absolute Rule 8` |
| `verified-fleet` HEAD at baseline | `75d915e3f07ae209ce4b5691977c5fdd18dd8be9` |
| Branch comparison immediately after approved fast-forward | `0 0` |
| Newer dependency manifest | Preserved by fast-forward; no code was omitted |
| Changes unique to `verified-fleet` | None |
| Working tree before first-run documentation | Clean |

Commands used: `git --no-optional-locks status --short`, `git --no-optional-locks branch --show-current`, `git --no-optional-locks rev-parse HEAD`, `git --no-optional-locks rev-parse verified-fleet`, `git --no-optional-locks rev-list --left-right --count verified-fleet...laya-decision`, `git --no-optional-locks log --oneline verified-fleet..laya-decision`, `git --no-optional-locks log --oneline laya-decision..verified-fleet`, and `git --no-optional-locks diff --stat verified-fleet..laya-decision`.

## Phase ledger

All phases were initialized as NOT RUN. Only Phase 0 and Phase 1 may be updated under the current authorization. Prior audit results are historical evidence, not execution of these phases.

| Phase | Scope | Status | Branch / last commit | Blocker / required user input |
| --- | --- | --- | --- | --- |
| 0 | Setup and safe full-suite baseline | PASS for isolated baseline; unrestricted external checks NOT RUN | `verified-fleet` / baseline `75d915e` | Fresh run: 214 passed, 13 skipped; see `reports/PHASE_0_REPORT.md` |
| 1 | Security and state gate, items 1.1-1.5 | NOT RUN | `verified-fleet` / baseline `75d915e` | Ready to begin after Phase 0 report/commit |
| 2 | Backtest integrity gate | NOT RUN | Not started | Outside current authorization |
| 3 | Operations and exchange | NOT RUN | Not started | Outside current authorization |
| 4 | Historical data | NOT RUN | Not started | Outside current authorization; Phases 1 and 2 must pass |
| 5 | Universe, costs and portfolio risk | NOT RUN | Not started | Outside current authorization |
| 6 | Research and long-window backtest | NOT RUN | Not started | Outside current authorization |
| 7 | Monitoring, ledger and runbook | NOT RUN | Not started | Outside current authorization |
| 8 | Laya classifier | NOT RUN | Not started | Outside current authorization; no model integration or training started |
| 9 | Repository evaluation | NOT RUN | Not started | Outside current authorization; no UI work started |

## Phase 0 observed setup and blockers

- Instruction ingestion and branch ancestry inspection are complete. The master-prompt body was compared byte-for-byte with its source extraction after writing.
- Fresh Phase 0 command: `python -B scripts/run_isolated_tests.py`. All 227 tests collected; 214 passed and 13 skipped in 25.51 seconds, exit 0. Five external-service checks were skipped by the safety policy; seven require an optional environment; one requires credential files deliberately excluded from the disposable copy.
- Baseline evidence: retained disposable directory `C:\Users\EKANTH~1\AppData\Local\Temp\zillers-phase-audit-y0dg41u9`, `test-output.txt` and `pytest.log`. No production account databases or credentials were copied. External/model requests were blocked.
- Read-only local Ollama health: HTTP 200, version 0.40.14. Testnet configuration is present, but exchange authentication was NOT RUN. Both Telegram owner settings are present; no values were exposed.
- `ACCOUNT_SIZE_USD` is not configured; default 1000 is used only in the disposable test environment and is not persisted to production configuration.
- No additional user input is needed to continue independent Phase 1 implementation. External-service verification requires separate narrow approval; no order execution is authorized.

## Phase 1 observed setup and blockers

- Items 1.1, 1.2, 1.3, 1.4 and 1.5 are all NOT RUN. No security code, production configuration, databases, reports, or Git history have been changed as Phase 1 implementation.
- Preserve the earlier handover's critical findings: emergency halt is not consistently shared across execution paths; exchange closing/reconciliation can diverge from local records; protective-stop failures can leave exposure. Ordinary passing tests do not establish trading safety.
- The previously observed paper process must not be stopped or reconfigured without permission. Its current state has not been rechecked in this first-run setup.
- Before any test, inspect external requests, credential use, order paths and persistent writes. Use disposable isolated data and block outbound requests. Existing permission for local read-only health checks does not authorize orders, messaging, public-service requests, or model inference.
- The existing `reports/.gitignore` ignores phase Markdown reports. Preserve it for now; phase-report versioning must be handled deliberately under the approved branch/commit plan.
- Phase 0 report: `reports/PHASE_0_REPORT.md`. Phase 1 report is not yet issued. Reports must use PASS / FAIL / NOT RUN per applicable numbered item and label stub-based evidence accurately.

## Required user input

Branch plan approved and applied. No branch decision is pending. Only Phases 0 and 1 are authorized. No external-service request, order, production configuration change, production state migration, bot restart, or history rewrite is authorized.

Do not supply secrets in chat. Any later request for credentials or external access must be narrow and tied to an authorized phase item.
