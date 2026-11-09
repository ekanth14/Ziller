"""Tests for Phase 7: Drift Monitoring, Telegram Alerts, and Accountant Trade Ledger."""

import csv
import io
import pytest

from cryptoscope.research.multi_coin.drift_monitor import (
    LiveDriftMonitor,
    DriftBaseline,
    DriftThresholds,
)
from cryptoscope.research.multi_coin.trade_ledger import (
    AccountantTradeLedger,
    ACCOUNTANT_DISCLAIMER,
)


def test_drift_monitor_slippage_drift_trigger():
    # Baseline expected: 8.5 bps, tolerance: +15 bps (max 23.5 bps)
    monitor = LiveDriftMonitor()
    
    # Record 5 fills with extreme slippage (30 bps each)
    for _ in range(5):
        monitor.record_fill(
            symbol="BTCUSDT",
            side="BUY",
            filled_notional_usd=100.0,
            nominal_price=80000.0,
            effective_price=80240.0,  # 30 bps higher
        )

    report = monitor.evaluate_drift()
    assert report.pause_engaged
    assert any("Slippage drift" in r for r in report.pause_reasons)
    
    # Telegram alert payload formatting
    alert_text = monitor.format_telegram_alert(report)
    assert "[DRIFT PAUSE ENGAGED]" in alert_text
    assert "Slippage drift" in alert_text

    # Clear pause
    monitor.clear_pause()
    assert not monitor.pause_engaged


def test_drift_monitor_fill_rate_trigger():
    monitor = LiveDriftMonitor()
    # Submit $1000 notional, but only fill $500 (50% fill rate < 85% threshold)
    monitor.record_order_submission(1000.0)
    monitor.record_fill("ETHUSDT", "BUY", 500.0, 3000.0, 3002.0)

    report = monitor.evaluate_drift()
    assert report.pause_engaged
    assert any("Fill rate" in r for r in report.pause_reasons)


def test_drift_monitor_drawdown_trigger():
    monitor = LiveDriftMonitor(initial_nav=1000.0)
    # Record position closure resulting in $890 NAV (11% drawdown >= 10% threshold)
    monitor.record_fill("SOLUSDT", "BUY", 200.0, 150.0, 150.1)
    monitor.record_position_closed("SOLUSDT", net_pnl_usd=-110.0, current_nav=890.0)

    assert monitor.pause_engaged
    assert any("Portfolio drawdown" in r for r in monitor.pause_reasons)


def test_accountant_trade_ledger_export(tmp_path):
    ledger = AccountantTradeLedger(fallback_usd_inr=85.0)

    ledger.record_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.0025,
        price_usdt=80000.0,
        fee_usdt=0.15,
        realized_pnl_usdt=0.0,
        order_id="11618423",
        execution_type="MARKET",
        usd_inr_rate=85.0,
    )

    ledger.record_entry(
        symbol="BTCUSDT",
        side="SELL",
        quantity=0.0025,
        price_usdt=81000.0,
        fee_usdt=0.1519,
        realized_pnl_usdt=2.50,
        order_id="11620699",
        execution_type="MARKET",
        usd_inr_rate=85.0,
    )

    out_csv = tmp_path / "test_ledger.csv"
    csv_str = ledger.export_csv(out_csv)

    # Verify disclaimer is on line 1
    lines = csv_str.strip().split("\n")
    assert lines[0] == ACCOUNTANT_DISCLAIMER

    # Verify column headers
    assert "timestamp_utc,symbol,side,quantity,price_usdt,fee_usdt,realized_pnl_usdt,usd_inr_rate,realized_pnl_inr,fee_inr,order_id,execution_type" in lines[1]

    # Verify numerical conversion
    # Realized PnL 2.50 USD * 85.0 INR = 212.50 INR
    assert "212.5" in lines[3]
    assert "11620699" in lines[3]
