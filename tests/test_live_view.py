"""Live Tradebot view: per-coin positions from real journal fills, live marks, totals, offline-safe."""
import sqlite3

from cryptoscope.desk.live_view import EXIT_FEE, PriceCache, build_live, coin_book


def _dbs(tmp_path):
    ex = sqlite3.connect(tmp_path / "orchestrator_execution.db")
    ex.execute("CREATE TABLE positions(symbol TEXT PRIMARY KEY, side TEXT, quantity REAL, entry_price REAL, stop_price REAL,"
               " target_price REAL, stop_order_id TEXT, created_at REAL, updated_at REAL, mode TEXT)")
    ex.execute("INSERT INTO positions VALUES('XRPUSDT','BUY',0.3,0.93,0.92,0.94,'s',300,300,'PAPER')")   # split row (old bug)
    ex.commit(); ex.close()
    j = sqlite3.connect(tmp_path / "trading_journal.db")
    j.execute("CREATE TABLE fills(timestamp REAL, fill_id TEXT, order_id TEXT, symbol TEXT, side TEXT, fill_price REAL,"
              " quantity REAL, fee_usd REAL, slippage_pct REAL, stop_order_id TEXT)")
    j.execute("CREATE TABLE positions_closed(timestamp REAL, symbol TEXT, side TEXT, entry_price REAL, exit_price REAL,"
              " quantity REAL, pnl_usd REAL, pnl_pct REAL, duration_seconds REAL, exit_reason TEXT)")
    for t in ("signals(timestamp REAL, symbol TEXT, direction TEXT, confidence REAL, strategy_id TEXT, reasons TEXT)",
              "debates(timestamp REAL, symbol TEXT, verdict TEXT, conviction_score REAL, risk_summary TEXT)",
              "meta_labels(timestamp REAL, symbol TEXT, thx02_p REAL, laya_p REAL, mean_p REAL, quality REAL, enforced INT, vetoed INT)",
              "risk_decisions(timestamp REAL, symbol TEXT, decision TEXT, veto_reasons TEXT, position_size_usd REAL)"):
        j.execute("CREATE TABLE " + t)
    j.executemany("INSERT INTO fills VALUES(?,?,?,?,?,?,?,?,0,NULL)", [
        (100, "a", "o", "XRPUSDT", "BUY", 0.90, 100, 0.09), (110, "b", "o", "XRPUSDT", "SELL", 0.91, 100, 0.09),
        (200, "c", "o", "XRPUSDT", "BUY", 0.92, 500, 0.46), (300, "d", "o", "XRPUSDT", "BUY", 0.93, 0.3, 0.0003)])
    j.execute("INSERT INTO positions_closed VALUES(110,'XRPUSDT','BUY',0.90,0.91,100,0.82,1.1,10,'TAKE_PROFIT')")
    j.execute("INSERT INTO risk_decisions VALUES(250,'BNBUSDT','VETOED','MAX_POSITIONS: 3 open; DEBATE_REJECT',500)")
    j.commit(); j.close()


class FakePrices(PriceCache):
    def __init__(self, marks):
        super().__init__(fetch=lambda path: [])
        self.marks = marks

    def prices(self, symbols):
        return {s: self.marks[s] for s in symbols if s in self.marks}

    def day_stats(self, symbols):
        return {s: {"open": self.marks[s] * 0.99} for s in symbols if s in self.marks}


def test_position_comes_from_all_buys_since_last_close(tmp_path):
    _dbs(tmp_path)
    b = coin_book(tmp_path, "XRPUSDT")
    p = b["position"]
    assert abs(p["quantity"] - 500.3) < 1e-9 and p["fills"] == 2               # not the 0.3 split row
    assert abs(p["entry"] - (0.92 * 500 + 0.93 * 0.3) / 500.3) < 1e-12
    assert p["opened_at"] == 200                                               # first buy, not the last
    assert b["realized"] == 0.82 and b["closed_trades"] == 1 and b["wins"] == 1


def test_build_live_marks_totals_and_status(tmp_path):
    _dbs(tmp_path)
    fleet = {"running": True, "mode": "PAPER", "symbols": ["XRPUSDT", "BNBUSDT"], "started_at": 50}
    d = build_live(tmp_path, fleet, FakePrices({"XRPUSDT": 0.95, "BNBUSDT": 600.0}), now=400)
    by = {c["symbol"]: c for c in d["coins"]}
    x = by["XRPUSDT"]
    cost = 0.92 * 500 + 0.93 * 0.3
    assert x["status"] == "IN POSITION" and abs(x["invested"] - (cost + 0.4603)) < 1e-9
    assert abs(x["upnl"] - ((0.95 * 500.3 - cost) - 0.4603 - 0.95 * 500.3 * EXIT_FEE)) < 1e-9
    assert abs(x["change_24h"] - (1 / 0.99 - 1)) < 1e-12
    assert by["BNBUSDT"]["status"].startswith("BLOCKED: MAX_POSITIONS") and "position" not in by["BNBUSDT"]
    assert d["coins"][0]["symbol"] == "XRPUSDT"                                 # held coins first
    assert d["totals"]["in_position"] == 1 and d["totals"]["coins"] == 2


def test_held_coin_shows_even_when_fleet_is_off(tmp_path):
    _dbs(tmp_path)
    d = build_live(tmp_path, {"running": False, "symbols": ["BNBUSDT"]}, FakePrices({"XRPUSDT": 0.9}))
    assert [c["symbol"] for c in d["coins"]] == ["XRPUSDT"] and d["running"] is False


def test_price_cache_batches_and_survives_errors():
    calls = []

    def fetch(path):
        calls.append(path)
        if "fail" in calls[0] and len(calls) > 1:
            raise OSError("down")
        return [{"symbol": "AUSDT", "price": "1.5"}, {"symbol": "BUSDT", "price": "2"}]
    pc = PriceCache(fetch=fetch, ttl=60)
    assert pc.prices(["AUSDT", "BUSDT"]) == {"AUSDT": 1.5, "BUSDT": 2.0}
    pc.prices(["BUSDT", "AUSDT"])
    assert len(calls) == 1 and "symbols=" in calls[0]                            # one batched call, then cached
    bad = PriceCache(fetch=lambda p: (_ for _ in ()).throw(OSError("x")))
    assert bad.prices(["AUSDT"]) == {} and bad.error == "OSError"
