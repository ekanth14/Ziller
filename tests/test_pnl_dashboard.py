"""P&L dashboard maths over the real journal / execution schemas (temporary databases)."""
import sqlite3

from cryptoscope.desk.pnl import build_pnl, trade_stats

DAY = 86400
NOW = 1_800_000_000.0


def _journal(path, closed, fills=(), vetoes=()):
    c = sqlite3.connect(path)
    c.executescript("""
      CREATE TABLE signals(timestamp REAL, signal_id TEXT, symbol TEXT, direction TEXT, confidence REAL, reasons TEXT, strategy_id TEXT);
      CREATE TABLE trade_intents(timestamp REAL, intent_id TEXT, symbol TEXT, direction TEXT, entry_price REAL, stop_loss REAL, take_profit REAL, strategy_id TEXT);
      CREATE TABLE debates(timestamp REAL, intent_id TEXT, symbol TEXT, verdict TEXT, conviction_score REAL, bull_thesis TEXT, bear_thesis TEXT, risk_summary TEXT);
      CREATE TABLE risk_decisions(timestamp REAL, intent_id TEXT, symbol TEXT, decision TEXT, veto_reasons TEXT, approved_quantity REAL, position_size_usd REAL, stop_distance_pct REAL);
      CREATE TABLE orders(timestamp REAL, order_id TEXT, intent_id TEXT, symbol TEXT, side TEXT, order_type TEXT, quantity REAL, price REAL, stop_price REAL, status TEXT);
      CREATE TABLE fills(timestamp REAL, fill_id TEXT, order_id TEXT, symbol TEXT, side TEXT, fill_price REAL, quantity REAL, fee_usd REAL, slippage_pct REAL, stop_order_id TEXT);
      CREATE TABLE positions_closed(timestamp REAL, symbol TEXT, side TEXT, entry_price REAL, exit_price REAL, quantity REAL, pnl_usd REAL, pnl_pct REAL, duration_seconds REAL, exit_reason TEXT);
    """)
    for t, sym, pnl, reason in closed:
        c.execute("INSERT INTO positions_closed VALUES (?,?,?,?,?,?,?,?,?,?)", (t, sym, "BUY", 10, 10 + pnl, 1, pnl, pnl * 10, 3600, reason))
    for i, fee in enumerate(fills):
        c.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?)", (NOW - i, f"f{i}", f"o{i}", "ADAUSDT", "BUY", 1.0, 10, fee, 0.05, None))
    for i, v in enumerate(vetoes):
        c.execute("INSERT INTO risk_decisions VALUES (?,?,?,?,?,?,?,?)", (NOW - i, f"i{i}", "ADAUSDT", "VETOED", v, 0, 0, 0))
    c.execute("INSERT INTO risk_decisions VALUES (?,?,?,?,?,?,?,?)", (NOW, "ok", "ADAUSDT", "APPROVED", "", 1, 10, 1))
    c.commit(); c.close()


def _positions(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE positions(symbol TEXT, side TEXT, quantity REAL, entry_price REAL, stop_price REAL, target_price REAL, stop_order_id TEXT, created_at REAL, updated_at REAL, mode TEXT)")
    for sym, qty, entry in rows:
        c.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?)", (sym, "BUY", qty, entry, entry * 0.97, entry * 1.06, None, NOW, NOW, "PAPER"))
    c.commit(); c.close()


def test_trade_stats_formulas():
    closed = [{"timestamp": 1, "pnl_usd": 30, "duration_seconds": 60}, {"timestamp": 2, "pnl_usd": -10, "duration_seconds": 60},
              {"timestamp": 3, "pnl_usd": -20, "duration_seconds": 60}, {"timestamp": 4, "pnl_usd": 50, "duration_seconds": 60}]
    s = trade_stats(closed, 1000)
    assert s["realized"] == 50 and s["win_rate"] == 0.5 and s["profit_factor"] == 80 / 30
    assert s["expectancy"] == 12.5 and s["best"] == 50 and s["worst"] == -20
    assert abs(s["max_drawdown"] - (1000 / 1030 - 1)) < 1e-12       # peak 1030 -> trough 1000
    assert s["streak"] == {"kind": "win", "count": 1}
    assert s["curve"][-1]["equity"] == 1050


def test_build_pnl_combines_fleet_open_positions_and_bots(tmp_path):
    _journal(tmp_path / "trading_journal.db",
             [(NOW - 40 * DAY, "ADAUSDT", 5.0, "TAKE_PROFIT"), (NOW - 3 * DAY, "XRPUSDT", -2.0, "STOP_LOSS"),
              (NOW - 60, "ADAUSDT", 1.0, "TAKE_PROFIT")],
             fills=[0.1, 0.2], vetoes=["Debate layer verdict is REJECT (Conviction: 0.0)",
                                       "MAX_OPEN_POSITIONS: Already holding 3 positions.; CORRELATION_CAP: x"])
    _positions(tmp_path / "orchestrator_execution.db", [("DOGEUSDT", 100, 0.10)])
    bots = [{"id": "b", "kind": "GRID", "symbol": "LINKUSDT", "status": "RUNNING", "pnl": 7.5, "equity": 107.5,
             "pnl_pct": 0.075, "config": {"investment": 100}}]
    d = build_pnl(tmp_path, bots, price=lambda s: 0.12, start_nav=1000, now=NOW)
    t = d["totals"]
    assert t["fleet_realized"] == 4.0 and abs(t["fleet_unrealized"] - 2.0) < 1e-9 and t["paper_bots"] == 7.5
    assert abs(t["net"] - 13.5) < 1e-9 and abs(t["fees"] - 0.3) < 1e-9
    assert abs(t["fleet_equity"] - 1006.0) < 1e-9 and t["bots_return"] == 0.075
    assert d["periods"]["7d"] == {"pnl": -1.0, "trades": 2} and d["periods"]["30d"]["trades"] == 2
    assert d["periods"]["all"]["trades"] == 3
    assert d["by_symbol"][0]["symbol"] == "XRPUSDT" and d["by_symbol"][-1]["pnl"] == 6.0
    pos = d["open_positions"][0]
    assert abs(pos["upnl_pct"] - 0.2) < 1e-9 and abs(pos["value"] - 12.0) < 1e-9
    reasons = {v["reason"]: v["count"] for v in d["top_vetoes"]}
    assert reasons == {"Debate layer verdict is REJECT": 1, "MAX_OPEN_POSITIONS": 1, "CORRELATION_CAP": 1}
    assert d["funnel"]["risk_approved"] == 1 and d["funnel"]["closed"] == 3


def test_build_pnl_without_any_databases(tmp_path):
    d = build_pnl(tmp_path, [], price=None, start_nav=500, now=NOW)
    assert d["status"] == "OK" and d["totals"]["net"] == 0 and d["equity_curve"] == [] and d["open_positions"] == []
    assert d["stats"]["win_rate"] is None and d["funnel"]["signals"] == 0


def test_unpriced_position_counts_as_unknown_not_zero_loss(tmp_path):
    _positions(tmp_path / "orchestrator_execution.db", [("ADAUSDT", 10, 1.0)])
    def boom(_):
        raise OSError("offline")
    d = build_pnl(tmp_path, [], price=boom, now=NOW)
    assert d["open_positions"][0]["upnl"] is None and d["totals"]["fleet_unrealized"] == 0
