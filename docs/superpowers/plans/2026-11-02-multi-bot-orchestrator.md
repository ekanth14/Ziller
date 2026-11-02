# Multi-Bot Autonomous Trading System with Telegram Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ZILLERS into an institutional multi-bot autonomous trading system orchestrated by an asyncio event bus with deterministic risk controls and a separate Telegram notifications gateway.

**Architecture:** 10 decoupled, single-responsibility bots (Data, Market Analyst, Quant, Strategy, Debate, Risk, Execution, Supervisor, Notifier, Journal) communicate purely through an asynchronous typed event bus. The pipeline strictly enforces `Strategy (TradeIntent) -> Debate (DebateResult) -> Risk (RiskDecision) -> Execution (OrderRequest/Fill)`. Only ExecutionBot imports exchange execution clients. Risk is 100% deterministic (no LLM). Supervisor monitors bot heartbeats, restarts crashed bots with exponential backoff, and triggers emergency protection if silent. Telegram runs as a resilient service with whitelisted access and local alert queuing.

**Tech Stack:** Python 3.12, `asyncio`, `dataclasses`, `sqlite3` (WAL mode), `python-telegram-bot` / HTTP async client, `pytest`.

**Spec:** User prompt requirements (Phases 1-5).

---

## Global Constraints
- **Paper & Testnet only during development:** Never place real-money orders.
- **Fail-closed:** Any timeout, feed drop, LLM failure, or safety ambiguity aborts the trade (`STAND_ASIDE` / `VETO`).
- **Exchange client isolation:** ONLY `ExecutionBot` may import or interact with the exchange trading client.
- **Deterministic risk controls:** Hard caps on daily loss, drawdown, per-coin exposure, and max open positions; never LLM-controlled.
- **Telegram security:** Owner chat ID whitelist only; mode changes to `LIVE` and risk limit increases are strictly impossible via Telegram.
- **Telegram resilience:** If Telegram is unreachable, trading continues and alerts queue locally.
- **State reconciliation:** Positions, orders, and bot states are persisted in SQLite and reconciled upon restart.

---

## Review Focus
1. **Exchange import leak:** Any bot other than `ExecutionBot` importing exchange/order clients. (Pinned by AST test).
2. **Supervisor heartbeat loss:** If SupervisorBot stops beating, ExecutionBot must immediately detect silence within 15s and protect/flatten positions.
3. **Debate timeout / LLM crash:** If local Ollama or Laya hangs, DebateBot must abort with `verdict='REJECT'` and zero trades placed.
4. **Daily loss limit breach:** RiskBot must veto all subsequent trade intents immediately once cumulative daily loss limit is hit.
5. **Telegram offline queue:** Ensure an outage of the Telegram API never blocks the asyncio event loop or drops alerts.

---

## Tasks

### Task 1: Typed Event Bus and Core Events (`cryptoscope/orchestrator/events.py` & `event_bus.py`)
- [ ] Create `cryptoscope/orchestrator/events.py` with typed dataclass events:
  - `MarketUpdate`, `Signal`, `TradeIntent`, `DebateResult`, `RiskDecision`, `OrderRequest`, `Fill`, `PositionClosed`, `SystemAlert`.
- [ ] Create `cryptoscope/orchestrator/event_bus.py`:
  - Asyncio pub/sub event bus supporting typed event subscriptions.
  - Isolated handler execution: an uncaught exception in one subscriber task must not crash the event bus or other subscribers.
  - Event history ring-buffer for telemetry and debugging.
- [ ] Write unit tests in `cryptoscope/tests/test_orchestrator_bus.py` testing subscription, concurrency, and failure isolation.
- [ ] Run pytest and verify green.
- [ ] Commit: `feat(orchestrator): add typed events and asynchronous event bus`.

### Task 2: BaseBot Interface and Supervisor Bot (`cryptoscope/orchestrator/base_bot.py` & `bots/supervisor_bot.py`)
- [ ] Create `cryptoscope/orchestrator/base_bot.py`:
  - `BaseBot` abstract base class with `start()`, `stop()`, `health()`, `on_event()`, `emit()`.
  - `BotHealth` dataclass tracking status (`HEALTHY`, `DEGRADED`, `CRITICAL`, `STOPPED`), error count, uptime, last heartbeat.
- [ ] Create `cryptoscope/orchestrator/bots/supervisor_bot.py`:
  - Periodically checks health of all registered bots (heartbeat interval = 3s).
  - Automatically restarts crashed bots with exponential backoff (1s, 2s, 4s, ... 30s) and emits `SystemAlert(severity='WARNING'/'CRITICAL')`.
  - Emits its own periodic supervisor heartbeat event (`SupervisorHeartbeat`).
- [ ] Write tests in `cryptoscope/tests/test_orchestrator_supervisor.py` verifying crash recovery and backoff.
- [ ] Run pytest and commit: `feat(orchestrator): add BaseBot interface and SupervisorBot with crash recovery`.

### Task 3: Data, Analyst, Quant, Strategy & Debate Bots (`cryptoscope/orchestrator/bots/`)
- [ ] Create `cryptoscope/orchestrator/bots/data_bot.py`:
  - Ingests feeds from existing `MarketDataAggregator` / `BinanceFeed` / `CandleStore`, emits `MarketUpdate`.
- [ ] Create `cryptoscope/orchestrator/bots/analyst_bot.py`:
  - Computes regimes, market structure, support/resistance, emits `Signal`.
- [ ] Create `cryptoscope/orchestrator/bots/quant_bot.py`:
  - Reuses `cryptoscope.quant` for pairs cointegration, OU half-life, Parkinson/GK/YZ volatility, CVD delta.
- [ ] Create `cryptoscope/orchestrator/bots/strategy_bot.py`:
  - Reuses `cryptoscope.autotrader.strategies` to propose `TradeIntent`.
- [ ] Create `cryptoscope/orchestrator/bots/debate_bot.py`:
  - Reuses `cryptoscope.agents.deliberation` to debate `TradeIntent`.
  - Fails closed to `REJECT` on LLM timeout (>200ms) or error.
- [ ] Write tests in `cryptoscope/tests/test_pipeline_bots.py`.
- [ ] Run pytest and commit: `feat(orchestrator): add Data, Analyst, Quant, Strategy, and Debate bots`.

### Task 4: Risk and Safety Bot (`cryptoscope/orchestrator/bots/risk_bot.py`)
- [ ] Create `cryptoscope/orchestrator/bots/risk_bot.py`:
  - 100% deterministic code (never LLM-driven).
  - Enforces: daily loss limit, max portfolio drawdown, max open positions, per-coin exposure cap, max order size, correlation cap, and 24h liquidity check.
  - Position sizing via fractional Kelly and volatility parity (`cryptoscope.quant.sizing`).
  - Emits `RiskDecision(decision='APPROVED' | 'VETOED', approved_quantity, risk_usd, veto_reasons)`.
- [ ] Write tests in `cryptoscope/tests/test_orchestrator_risk.py` verifying all 7 risk limits.
- [ ] Run pytest and commit: `feat(orchestrator): add deterministic RiskBot with hard safety limits`.

### Task 5: Execution Bot & Exchange Isolation Guard (`cryptoscope/orchestrator/bots/execution_bot.py`)
- [ ] Create `cryptoscope/orchestrator/bots/execution_bot.py`:
  - ONLY bot in the system permitted to import exchange trading clients.
  - Supports autonomy modes: `OBSERVE`, `PAPER`, `TESTNET`, `LIVE` (gated by existing 5-gate governor).
  - Places both entry order AND exchange-level stop-loss order.
  - Heartbeat watchdog: If `SupervisorHeartbeat` is missing for > 15s, transitions to emergency protection (cancels orders, flattens or tightens stops).
  - Reconciles open positions and orders from SQLite state store upon restart.
- [ ] Create `cryptoscope/tests/test_exchange_isolation.py`:
  - Static AST audit test verifying no file under `cryptoscope/orchestrator/bots/` except `execution_bot.py` imports exchange trading modules or creates order requests directly.
- [ ] Write tests in `cryptoscope/tests/test_orchestrator_execution.py`.
- [ ] Run pytest and commit: `feat(orchestrator): add ExecutionBot with stop-loss orders and AST isolation test`.

### Task 6: Journal and Notifier Bots (`cryptoscope/orchestrator/bots/journal_bot.py` & `notifier_bot.py`)
- [ ] Create `cryptoscope/orchestrator/bots/journal_bot.py`:
  - Logs all signals, debate results, veto reasons, fills, and position closures with timestamps to SQLite `trading_journal.db`.
  - Calculates daily/weekly performance metrics: win rate, expectancy $E[R]$, max drawdown, fees, slippage.
- [ ] Create `cryptoscope/orchestrator/bots/notifier_bot.py`:
  - Subscribes to alerts, fills, closures, and reports.
  - Enforces rate limiting and alert batching to prevent notification floods.
  - Dispatches to the Telegram gateway service or local spool buffer.
- [ ] Write tests in `cryptoscope/tests/test_journal_and_notifier.py`.
- [ ] Run pytest and commit: `feat(orchestrator): add JournalBot and NotifierBot`.

### Task 7: Telegram Autonomous Gateway (`cryptoscope/telegram/`)
- [ ] Create `cryptoscope/telegram/bot.py` and `service.py`:
  - Connects to Telegram Bot API with token from `TELEGRAM_BOT_TOKEN`.
  - Whitelist: strictly checks `chat_id == TELEGRAM_OWNER_CHAT_ID`; silently ignores unauthorized users.
  - Commands: `/status`, `/positions`, `/pnl`, `/pause`, `/resume`, `/kill`, `/flatten`.
  - Inline keyboards for Pause and Flatten confirmation.
  - Safety rule: commands cannot raise risk limits or change autonomy mode to `LIVE`.
  - Resilient offline spooling: if Telegram is unreachable, trading continues and alerts queue locally without dropping.
- [ ] Write tests in `cryptoscope/tests/test_telegram_gateway.py`.
- [ ] Run pytest and commit: `feat(telegram): add Telegram gateway with whitelist, commands, and offline spooling`.

### Task 8: End-to-End Historical Replay and Failure Mode Tests
- [ ] Create `cryptoscope/tests/test_multi_bot_e2e.py`:
  - Real candle historical replay through the complete 10-bot event pipeline.
  - Comprehensive failure injection tests:
    - Feed down -> DataBot reports degraded -> StrategyBot stands aside.
    - Ollama / Laya down -> DebateBot rejects with `STAND_ASIDE`.
    - Laya timeout (>200ms) -> DebateBot triggers fast fallback.
    - Exchange rejection -> ExecutionBot catches error cleanly, raises alert.
    - Duplicate signal -> Deduplicated, no double fill.
    - Restart mid-position -> Reconciles SQLite positions before trading resumes.
    - Telegram down -> Alerts queue locally, trading loop continues uninterrupted.
    - Supervisor silent -> ExecutionBot heartbeat watchdog triggers protect mode.
    - Daily loss limit breach -> RiskBot vetoes subsequent trades.
    - AST isolation enforcement -> Asserts ONLY `ExecutionBot` imports exchange execution.
- [ ] Run full test suite and verify 100% green.
- [ ] Commit: `test(orchestrator): add end-to-end historical replay and failure injection test suite`.

### Task 9: Final Integration, Packaging & Multi-Bot Verification Report
- [ ] Update `cryptoscope/dashboard/__main__.py` or CLI start script to optionally launch the multi-bot orchestrator.
- [ ] Update `README.md` and `.env.example` with Telegram configuration (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`).
- [ ] Generate comprehensive `MULTI_BOT_PRODUCTION_REPORT.md` with benchmark evidence and test results table.
- [ ] Commit and present deliverable to the user.
