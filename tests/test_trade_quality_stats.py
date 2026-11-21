"""P&L quality stats: break-even win rate and per-trade Sharpe."""
from cryptoscope.desk.pnl import trade_stats


def _t(i, pnl):
    return {"timestamp": 1000 + i, "pnl_usd": pnl, "duration_seconds": 60}


def test_breakeven_win_rate_and_sharpe():
    # avg win 3, avg loss 7 -> must win 70% of trades just to break even; actual win rate is 50%
    s = trade_stats([_t(0, 3), _t(1, -7), _t(2, 3), _t(3, -7)], 10_000)
    assert abs(s["breakeven_win_rate"] - 0.7) < 1e-9 and s["win_rate"] == 0.5
    assert s["sharpe_per_trade"] is not None and s["sharpe_per_trade"] < 0


def test_stats_with_no_trades():
    s = trade_stats([], 10_000)
    assert s["breakeven_win_rate"] is None and s["sharpe_per_trade"] is None


def test_pnl_split_by_scanner_tier(tmp_path):
    import json
    from cryptoscope.desk.pnl import by_tier, load_tier_log, tier_for
    log_path = tmp_path / "scanner_tiers.jsonl"
    log_path.write_text("\n".join([
        json.dumps({"at": 1000, "tiers": {"AUSDT": "TREND", "BUSDT": "POTENTIAL"}}),
        "not json",
        json.dumps({"at": 2000, "tiers": {"AUSDT": "SHORT_TERM"}}),
    ]), encoding="utf-8")
    log = load_tier_log(log_path)
    assert tier_for("AUSDT", 1500, log) == "TREND" and tier_for("AUSDT", 2500, log) == "SHORT_TERM"
    assert tier_for("BUSDT", 2500, log) == "POTENTIAL" and tier_for("CUSDT", 2500, log) == "UNKNOWN"
    closed = [{"symbol": "AUSDT", "timestamp": 1500, "pnl_usd": 5, "duration_seconds": 1},
              {"symbol": "BUSDT", "timestamp": 1600, "pnl_usd": -3, "duration_seconds": 1},
              {"symbol": "BUSDT", "timestamp": 1700, "pnl_usd": -2, "duration_seconds": 1}]
    rows = {r["tier"]: r for r in by_tier(closed, log, 10_000)}
    assert [r["tier"] for r in by_tier(closed, log, 10_000)] == ["TREND", "POTENTIAL"]
    assert rows["TREND"]["realized"] == 5 and rows["POTENTIAL"]["trades"] == 2 and rows["POTENTIAL"]["win_rate"] == 0
    assert load_tier_log(tmp_path / "missing.jsonl") == []


def test_autopilot_records_tiers_on_start(tmp_path):
    from cryptoscope.desk.scanner import Autopilot

    class Scan:
        def scan(self, mode, force=False):
            return {"top": ["AUSDT", "BUSDT"], "tiers": {"TREND": ["AUSDT"], "SHORT_TERM": [], "POTENTIAL": ["BUSDT"]}}

    class Fleet:
        def status(self):
            return {"running": False}

        def start(self, *a):
            pass
    log = tmp_path / "t.jsonl"
    Autopilot(Scan(), Fleet(), lambda: 0, tier_log=log)._cycle("admin", first=True)
    import json
    assert json.loads(log.read_text())["tiers"] == {"AUSDT": "TREND", "BUSDT": "POTENTIAL"}
