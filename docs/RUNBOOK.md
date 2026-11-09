# Autonomous Quantitative Fleet: Production Operations Runbook

**System**: Quantitative Fleet (`cryptoscope/`, repo `zien-crypto`)  
**Target Environments**: Windows Host / Ubuntu Linux Always-On VPS  
**Trading Modes**: Paper & Binance Spot Testnet ONLY (`LIVE_TRADING=false` strictly enforced)  
**Safety Invariant**: Zero secret printing in logs or terminal; deterministic 5-gate governor must never be bypassed.

---

## 1. System Architecture & Component Map

| Component | Responsibility | Standard Port / Endpoint | Health Check |
| --- | --- | --- | --- |
| **Dashboard** | Web observability UI & admin controls | `http://localhost:8900` | `GET /health`, `GET /ready` |
| **Orchestrator** | Multi-bot event bus (9 autonomous agents) | Background Daemon | Bus heartbeat event, `work/logs/testnet_7day_run.log` |
| **RiskBot** | Deterministic 5-gate exposure & circuit breaker | In-process | Peak drawdown (<10%), daily loss (<3%) |
| **Drift Monitor** | Live-vs-backtest slippage and fill sentinel | In-process | `reports/PHASE_7_DRIFT_REPORT.json` |
| **Local Model Cache** | Fast local debate & classifier serving | `http://localhost:11434` | `GET http://localhost:11434/api/tags` |
| **SQLite WAL Backups** | Hourly automated snapshot rotation | In-process worker | `work/backups/hourly/` |

---

## 2. Emergency Operational Commands

### 2.1 Emergency Kill Switch
To halt all order generation and cancel pending working orders:
- **Via Local Dashboard**: Click `[EMERGENCY KILL SWITCH]` on `http://localhost:8900/`.
- **Via CLI / Terminal**:
  ```bash
  python -m cryptoscope.execution.lifecycle --halt-flatten
  ```
- **Via Telegram**: Send `/kill` to the configured Telegram bot.  
  *Note*: Under Phase 1 & Phase 3 hardening, `/resume` via Telegram is **permanently disabled**. Resuming trading can ONLY occur via local dashboard with admin re-authentication.

### 2.2 Resuming Trading After a Halt
1. Navigate to `http://localhost:8900/admin`.
2. Inspect the latch status (`HALT_FLATTEN` or `DRAWDOWN_CIRCUIT`).
3. Verify exchange open orders are zero:
   ```bash
   python scripts/run_phase3_testnet_checks.py
   ```
4. Authenticate with admin credentials and click `[RESET EMERGENCY LATCH]`.

---

## 3. Incident Troubleshooting ("What to do when X breaks")

### Case A: Binance API Key Rejection (`-2015 Invalid API-key, IP, or permissions`)
- **Symptoms**: Orchestrator logs `BinanceAPIException: -2015`. Orders rejected.
- **Root Causes**:
  1. Testnet key expired (Binance Spot Testnet keys are cycled periodically).
  2. Trailing spaces, newlines, or quote characters in `.env`.
  3. Environment variable mismatch (`BINANCE_ENV="testnet"` vs `BINANCE_ENV="live"`).
- **Resolution**:
  1. Open `.env` and verify `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET`.
  2. Ensure no whitespace or quotes surround values.
  3. Test read-only authentication without printing keys:
     ```bash
     python -c "from cryptoscope.execution.binance_testnet import BinanceTestnetClient; c = BinanceTestnetClient(); print('Ping:', c.ping())"
     ```
  4. If invalid, obtain a fresh key from `https://testnet.binance.vision/` and update `.env`.

### Case B: Binance Rate Limit (`HTTP 429` / `HTTP 418 IP Ban`)
- **Symptoms**: Requests fail with status code 429; orchestrator enters exponential cooldown.
- **Root Causes**: Request weight exceeded 1200 weight/minute.
- **Resolution**:
  1. `BinanceTestnetClient._request` automatically latches `retry_after_monotonic`. Do NOT restart the bot repeatedly (restarting resets the client-side cooldown and risks an IP ban).
  2. Verify the cooldown in `work/logs/testnet_7day_run.log`.
  3. Once cooldown expires, the client resumes normal requests automatically.

### Case C: SQLite Database Locked / WAL Corruption
- **Symptoms**: `sqlite3.OperationalError: database is locked` in `work/runtime/*.db`.
- **Resolution**:
  1. Check for zombie background processes accessing the DB:
     ```powershell
     Get-Process python | Select-Object Id, ProcessName, StartTime
     ```
  2. Verify WAL mode is intact:
     ```bash
     python -c "import sqlite3; con = sqlite3.connect('work/runtime/orders.db'); print(con.execute('PRAGMA journal_mode;').fetchone())"
     ```
  3. If corrupted, restore from the latest verified hourly backup in `work/backups/hourly/`.

### Case D: Telegram Unauthorized Access / Spam Messages
- **Symptoms**: Bot receives messages from unknown user or group chat.
- **Resolution**:
  - `cryptoscope/telegram/gateway.py` strictly whitelists BOTH `TELEGRAM_OWNER_ID` and `TELEGRAM_CHAT_ID`. Unauthorized users receive zero response and commands are dropped.
  - If the bot was accidentally added to a public group:
    1. Open Telegram, open the group settings, and remove the bot.
    2. In `.env`, ensure `TELEGRAM_CHAT_ID` matches your private user ID.

### Case E: Ollama / Local Model Timeout or Unreachable
- **Symptoms**: Consensus debate logs `TimeoutError: Deadline exceeded (35s)` or HTTP connection refused.
- **Resolution**:
  1. Verify Ollama is running:
     ```powershell
     curl http://localhost:11434/api/tags
     ```
  2. If down, restart Ollama:
     ```powershell
     ollama serve
     ```
  3. Deterministic safety guarantee: When the model times out, the system fails closed (`STAND_ASIDE`), meaning zero trades are placed without consensus.

### Case F: Live Drift Pause Engaged (`DRIFT_PAUSE`)
- **Symptoms**: Telegram alert: `🚨 [DRIFT PAUSE ENGAGED]`. New entry orders blocked.
- **Root Causes**: Slippage drift > 15 bps, fill rate < 85%, or win rate < 25%.
- **Resolution**:
  1. Review drift diagnostics:
     ```bash
     python -c "from cryptoscope.research.multi_coin.drift_monitor import LiveDriftMonitor; m = LiveDriftMonitor(); print(m.evaluate_drift())"
     ```
  2. If exchange orderbook depth has temporarily collapsed, pause trading until spread normalizes.
  3. Clear pause from dashboard or via `m.clear_pause()`.

---

## 4. Deployment Notes for Always-On Machine

### 4.1 Windows Host (Task Scheduler Setup)
To ensure the autonomous fleet starts automatically upon machine reboot:
1. Open PowerShell as Administrator.
2. Create an auto-restart scheduled task:
   ```powershell
   $Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "-u -m cryptoscope.orchestrator --mode TESTNET --symbols BTCUSDT ETHUSDT SOLUSDT" -WorkingDirectory "C:\Users\Ekanth's laptop\Desktop\my projects\zien-crypto"
   $Trigger = New-ScheduledTaskTrigger -AtStartup
   $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
   $Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Days 30)
   Register-ScheduledTask -TaskName "ZillersAutonomousFleet" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings
   ```

### 4.2 Linux VPS (`systemd` Unit Setup)
Create `/etc/systemd/system/zillers-fleet.service`:
```ini
[Unit]
Description=Zillers Quantitative Trading Fleet
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/zien-crypto
ExecStart=/opt/zien-crypto/venv/bin/python -u -m cryptoscope.orchestrator --mode TESTNET --symbols BTCUSDT ETHUSDT SOLUSDT
Restart=always
RestartSec=10
EnvironmentFile=/opt/zien-crypto/.env
StandardOutput=append:/opt/zien-crypto/work/logs/testnet_7day_run.log
StandardError=append:/opt/zien-crypto/work/logs/testnet_7day_run.log

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable zillers-fleet
sudo systemctl start zillers-fleet
```

---

## 5. Accountant Trade Ledger Export Protocol

At month-end or fiscal year-end:
1. Run the trade ledger export utility:
   ```bash
   python scripts/run_phase7_operations_and_ledger.py --export-ledger
   ```
2. The sanitized CSV is written to `reports/ACCOUNTANT_TRADE_LEDGER.csv`.
3. Verify that the top line includes the statutory non-tax-advice disclaimer.
4. Transfer `reports/ACCOUNTANT_TRADE_LEDGER.csv` to your Chartered Accountant / CPA.
