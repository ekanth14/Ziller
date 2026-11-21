"""One position per coin: no stacked entries, no overwritten positions, split PAPER positions repaired."""
import asyncio
import json
import sqlite3

from cryptoscope.execution.paper_repair import repair_paper_positions
from cryptoscope.orchestrator.bots.risk_bot import RiskBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import Fill, TradeIntent


def _intent(sym="UNIUSDT"):
    return TradeIntent(symbol=sym, direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.01)


def test_risk_bot_vetoes_a_second_entry_on_a_held_coin():
    bot = RiskBot(EventBus(), max_entries_per_day=50)
    assert bot.check_pre_trade_risk(_intent())[0]
    bot._handle_fill(Fill(symbol="UNIUSDT", side="BUY", quantity=100, executed_price=1.0))
    ok, why = bot.check_pre_trade_risk(_intent())
    assert not ok and any(r.startswith("ALREADY_IN_POSITION") for r in why)
    assert bot.check_pre_trade_risk(_intent("XRPUSDT"))[0]


def test_restored_positions_count_toward_limits():
    bot = RiskBot(EventBus(), max_open_positions=1)
    bot.seed_open_positions({"NEARUSDT": {"quantity": 517.4, "entry_price": 2.9, "side": "BUY"},
                             "BAD": {"quantity": "x"}})
    assert set(bot.open_positions) == {"NEARUSDT"} and abs(bot.open_positions["NEARUSDT"]["usd_value"] - 1500.46) < 0.01
    ok, why = bot.check_pre_trade_risk(_intent("NEARUSDT"))
    assert not ok and any("ALREADY_IN_POSITION" in r for r in why)


def test_execution_bot_refuses_to_overwrite_an_open_position(tmp_path):
    from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot
    from cryptoscope.orchestrator.events import RiskDecision

    class NotHalted:
        def snapshot(self):
            return {"halted": False}

        def halt(self, *a):
            raise AssertionError("must not halt")

    bot = ExecutionBot(EventBus(), mode="PAPER", db_path=str(tmp_path / "ex.db"))
    bot.halt_state = NotHalted()
    out = []

    async def emit(ev):
        out.append(ev)
    bot.emit = emit

    async def buy(qty):
        it = _intent()
        bot.cached_intents[it.intent_id] = it
        await bot._execute_approved_trade(RiskDecision(intent_id=it.intent_id, symbol="UNIUSDT", decision="APPROVED",
                                                       approved_quantity=qty, position_size_usd=qty))
    asyncio.run(buy(100))
    asyncio.run(buy(5))
    assert bot.active_positions["UNIUSDT"]["quantity"] == 100
    assert sum(1 for e in out if isinstance(e, Fill)) == 1


def test_repair_rebuilds_split_paper_positions(tmp_path):
    ex, jr = tmp_path / "ex.db", tmp_path / "j.db"
    c = sqlite3.connect(ex)
    c.execute("CREATE TABLE positions(symbol TEXT PRIMARY KEY, side TEXT, quantity REAL, entry_price REAL, stop_price REAL,"
              " target_price REAL, stop_order_id TEXT, created_at REAL, updated_at REAL, mode TEXT)")
    c.execute("CREATE TABLE position_details(symbol TEXT PRIMARY KEY, payload TEXT)")
    c.execute("INSERT INTO positions VALUES('UNIUSDT','BUY',2,5.0,4.9,5.1,'s',0,0,'PAPER')")
    c.execute("INSERT INTO positions VALUES('ADAUSDT','BUY',10,1.0,0.9,1.1,'s',0,0,'TESTNET')")
    c.execute("INSERT INTO position_details VALUES('UNIUSDT', ?)", (json.dumps({"quantity": 2, "entry_price": 5.0}),))
    c.commit(); c.close()
    j = sqlite3.connect(jr)
    j.execute("CREATE TABLE fills(timestamp REAL, fill_id TEXT, order_id TEXT, symbol TEXT, side TEXT, fill_price REAL,"
              " quantity REAL, fee_usd REAL, slippage_pct REAL, stop_order_id TEXT)")
    j.execute("CREATE TABLE positions_closed(timestamp REAL, symbol TEXT, side TEXT, entry_price REAL, exit_price REAL,"
              " quantity REAL, pnl_usd REAL, pnl_pct REAL, duration_seconds REAL, exit_reason TEXT)")
    j.executemany("INSERT INTO fills VALUES(?,?,?,?,?,?,?,0,0,NULL)", [
        (10, "a", "o", "UNIUSDT", "BUY", 4.0, 50), (11, "b", "o", "UNIUSDT", "SELL", 4.1, 50),   # earlier, closed
        (20, "c", "o", "UNIUSDT", "BUY", 4.0, 100), (21, "d", "o", "UNIUSDT", "BUY", 5.0, 2)])   # current, split
    j.commit(); j.close()
    fixed = repair_paper_positions(ex, jr)
    assert [f["symbol"] for f in fixed] == ["UNIUSDT"]                      # TESTNET row untouched
    row = sqlite3.connect(ex).execute("SELECT quantity, entry_price FROM positions WHERE symbol='UNIUSDT'").fetchone()
    assert row[0] == 102 and abs(row[1] - (400 + 10) / 102) < 1e-9
    payload = json.loads(sqlite3.connect(ex).execute("SELECT payload FROM position_details").fetchone()[0])
    assert payload["quantity"] == 102
    assert repair_paper_positions(ex, jr) == []                             # idempotent
