import pytest
from core.quant.berkshire_committee import BerkshireCommittee

def test_berkshire_committee_evaluation():
    committee = BerkshireCommittee()
    data = {
        "market_cap": 1200000000000,
        "daily_volume": 35000000000,
        "staking_yield_pct": 0.0,
        "active_addresses": 950000,
        "hashrate_eh": 650.0,
        "annual_network_fees": 800000000,
        "developer_count": 450,
        "top_holders_share_pct": 0.12,
    }
    report = committee.audit_asset("BTCUSDT", data)
    assert report["symbol"] == "BTCUSDT"
    assert "duan_moat" in report
    assert "buffett_valuation" in report
    assert "munger_inversion" in report
    assert "lilu_integrity" in report
    assert report["rigor_passed"] is True
    assert "composite_conviction_score" in report
    assert 0.0 <= report["composite_conviction_score"] <= 100.0

def test_berkshire_committee_missing_data():
    committee = BerkshireCommittee()
    report = committee.audit_asset("UNKNOWN", {})
    assert report["symbol"] == "UNKNOWN"
    assert report["rigor_passed"] is False
    assert report["composite_conviction_score"] == 0.0
