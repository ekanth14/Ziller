"""Unit tests for position sizing: Fixed Fractional Risk and Kelly gating (Phase 2)."""

import pytest
from cryptoscope.quant.sizing import (
    fixed_fractional_sizing,
    optimal_trade_sizing,
    kelly_criterion,
)


def test_fixed_fractional_sizing_standard():
    balance = 10000.0
    entry = 60000.0
    stop = 58800.0  # 2.0% stop distance
    
    res = fixed_fractional_sizing(
        account_balance=balance,
        entry_price=entry,
        stop_loss=stop,
        risk_fraction=0.005,  # 0.5%
    )
    assert res["status"] == "APPROVED"
    assert res["sizing_mode"] == "FIXED_FRACTIONAL"
    assert res["risk_usd"] == 50.0  # 0.5% of $10,000
    assert abs(res["risk_pct"] - 0.5) < 0.01
    assert abs(res["position_size_usd"] - 2500.0) < 0.1
    assert abs(res["position_qty"] - (2500.0 / 60000.0)) < 1e-5


def test_fixed_fractional_sizing_tight_stop_flooring():
    balance = 10000.0
    entry = 100.0
    stop = 99.9  # 0.1% stop -> below 0.5% minimum floor
    
    res = fixed_fractional_sizing(
        account_balance=balance,
        entry_price=entry,
        stop_loss=stop,
        risk_fraction=0.005,
        max_account_cap_pct=0.50,
    )
    assert res["status"] == "APPROVED"
    # Notional capped at 50% of balance = $5,000
    assert res["position_size_usd"] <= 5000.0
    assert res["stop_distance_pct"] == 0.10


def test_optimal_trade_sizing_defaults_to_fixed_fractional():
    # Calling without any explicit mode should default to FIXED_FRACTIONAL
    res = optimal_trade_sizing(
        account_balance=10000.0,
        entry_price=2000.0,
        stop_loss=1960.0,  # 2% stop
    )
    assert res["status"] == "APPROVED"
    assert res["sizing_mode"] == "FIXED_FRACTIONAL"
    assert res["risk_usd"] == 50.0  # 0.5% of 10k
    assert res["kelly_gated"] is True


def test_kelly_gating_when_flag_disabled():
    # Sizing mode requested is KELLY, but flag is False
    res = optimal_trade_sizing(
        account_balance=10000.0,
        entry_price=2000.0,
        stop_loss=1960.0,
        sizing_mode="KELLY",
        enable_kelly_sizing=False,
        closed_trades_count=500,
    )
    assert res["status"] == "APPROVED"
    assert res["sizing_mode"] == "FIXED_FRACTIONAL"
    assert res["kelly_gated"] is True
    assert "disabled" in res["gating_reason"]


def test_kelly_gating_when_trade_count_below_300():
    # Sizing mode requested is KELLY, flag is True, but trades < 300
    res = optimal_trade_sizing(
        account_balance=10000.0,
        entry_price=2000.0,
        stop_loss=1960.0,
        sizing_mode="KELLY",
        enable_kelly_sizing=True,
        closed_trades_count=299,
    )
    assert res["status"] == "APPROVED"
    assert res["sizing_mode"] == "FIXED_FRACTIONAL"
    assert res["kelly_gated"] is True
    assert "300" in res["gating_reason"]


def test_kelly_active_when_both_conditions_met():
    # Sizing mode KELLY, flag True, trades >= 300
    res = optimal_trade_sizing(
        account_balance=10000.0,
        entry_price=2000.0,
        stop_loss=1960.0,
        sizing_mode="KELLY",
        enable_kelly_sizing=True,
        closed_trades_count=350,
        win_rate=0.55,
        win_loss_ratio=2.0,
    )
    assert res["status"] == "APPROVED"
    assert res["sizing_mode"] == "KELLY"
    assert res["kelly_gated"] is False
    assert "kelly_metrics" in res


def test_sizing_invalid_inputs():
    assert optimal_trade_sizing(0, 100, 95)["status"] == "INVALID_PARAMETERS"
    assert optimal_trade_sizing(10000, 0, 95)["status"] == "INVALID_PARAMETERS"
    assert optimal_trade_sizing(10000, 100, 100)["status"] == "INVALID_PARAMETERS"
    assert fixed_fractional_sizing(0, 100, 95)["status"] == "INVALID_PARAMETERS"
