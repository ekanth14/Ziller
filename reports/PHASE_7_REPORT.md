# Phase 7: Monitoring, Runbook, and Accountant Ledger Report

Generated: [REDACTED]-11-09 13:58:08 UTC
Branch: `multi-coin`
Status: **PASS**

## 1. Live-vs-Backtest Drift Sentinel (Phase 7.1)

- **Baseline Metrics (derived from Phase 6 backtest)**:
  - Expected Slippage: 8.5 bps
  - Expected Fill Rate: 95.0%
  - Expected Win Rate: 45.0%
  - Max Allowable Drawdown: 10.0%
- **Tolerances & Automated Circuit**:
  - Max Slippage Drift: +15.0 bps
  - Min Fill Rate: 85.0%
  - Min Win Rate: 25.0% (over >= 15 trades)
  - Hard Drawdown Cap: 10.0%
- **Status on Observed Orders**:
  - Realized Slippage: 1.5 bps
  - Fill Rate: 100.0%
  - Pause Engaged: **False** (Execution strictly within normal bounds)
  - Telegram alert payload: Formatted and sanitized with zero token or secret exposure.

## 2. Production Runbook (Phase 7.2)

- **Comprehensive Runbook Created**: [`docs/RUNBOOK.md`](file:///c:/Users/Ekanth's%20laptop/Desktop/my%20projects/zien-crypto/docs/RUNBOOK.md)
- **Incident Troubleshooting Procedures Documented**:
  - Binance API key -2015 invalid key handling
  - Binance HTTP 429 / 418 rate-limit exponential backoff
  - SQLite WAL recovery and hourly backup restoration
  - Telegram unauthorized user defense and owner ID whitelisting
  - Local model / Ollama timeout and fail-closed `STAND_ASIDE` handling
  - Drift pause recovery procedures (admin dashboard re-authentication only)
- **Always-On Deployment Specifications**:
  - Windows Host: Auto-start scheduled task via PowerShell
  - Linux VPS: systemd service unit definition (`zillers-fleet.service`) with auto-restart

## 3. Accountant Trade Ledger Export (Phase 7.3)

- **Artifact**: `reports/ACCOUNTANT_TRADE_LEDGER.csv`
- **Fields**: `timestamp_utc, symbol, side, quantity, price_usdt, fee_usdt, realized_pnl_usdt, usd_inr_rate, realized_pnl_inr, fee_inr, order_id, execution_type`
- **FX Integration**: Real-time USD/INR rate lookup via `FxRateService` with reference fallback (84.50 INR/USD).
- **Compliance Guarantee**: Line 1 explicitly includes the non-tax-advice statutory disclosure.
