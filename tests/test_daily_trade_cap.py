"""RiskBot caps NEW positions per UTC day (fees make overtrading the main way small bots lose)."""
from cryptoscope.orchestrator.bots.risk_bot import RiskBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import Fill, TradeIntent


def _intent(sym):
    return TradeIntent(symbol=sym, direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.01)


def test_cap_blocks_new_entries_but_not_open_symbols(tmp_path):
    bot = RiskBot(EventBus(), max_entries_per_day=2, state_path=str(tmp_path / "risk.json"))
    for sym in ("AUSDT", "BUSDT"):
        assert bot.check_pre_trade_risk(_intent(sym))[0]
        bot._handle_fill(Fill(symbol=sym, side="BUY", quantity=1.0, executed_price=1.0))
    ok, why = bot.check_pre_trade_risk(_intent("CUSDT"))
    assert not ok and any(r.startswith("MAX_DAILY_TRADES") for r in why)
    assert bot.check_pre_trade_risk(_intent("AUSDT"))[0]          # already open: not a new entry
    bot._handle_fill(Fill(symbol="AUSDT", side="BUY", quantity=1.0, executed_price=1.0))
    assert bot.daily_entries == 2

    # survives a restart the same day, resets on a new UTC day
    again = RiskBot(EventBus(), max_entries_per_day=2, state_path=str(tmp_path / "risk.json"))
    assert again.daily_entries == 2 and not again.check_pre_trade_risk(_intent("CUSDT"))[0]
    again._day = "1999-01-01"
    assert again.check_pre_trade_risk(_intent("CUSDT"))[0] and again.daily_entries == 0


def test_cap_comes_from_env(monkeypatch):
    monkeypatch.setenv("ZILLERS_MAX_TRADES_PER_DAY", "5")
    assert RiskBot(EventBus()).max_entries_per_day == 5
    monkeypatch.setenv("ZILLERS_MAX_TRADES_PER_DAY", "junk")
    assert RiskBot(EventBus()).max_entries_per_day == 12
