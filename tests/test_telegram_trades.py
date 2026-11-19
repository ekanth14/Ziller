"""Telegram trade notifications: formatting, correlation, escaping, and the one-shot sender (no network)."""
import asyncio
import json

from cryptoscope.orchestrator.bots.notifier_bot import NotifierBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import Fill, PositionClosed, SystemAlert, TradeIntent
from cryptoscope.telegram import notify


class _Fx:
    def get_rate(self, target):
        return {"status": "available", "rate": 90.0}


def _drain(bot):
    out = []
    while not bot.outbox_queue.empty():
        out.append(bot.outbox_queue.get_nowait().text)
    return out


def test_fill_message_has_mode_ist_inr_and_the_right_intent():
    async def run():
        bot = NotifierBot(EventBus(), mode="TESTNET", fx_service=_Fx())
        old = TradeIntent(symbol="BTCUSDT", direction="BUY", entry_price=100, stop_loss=90, take_profit=120, strategy_id="old")
        new = TradeIntent(symbol="BTCUSDT", direction="BUY", entry_price=100, stop_loss=95, take_profit=130, strategy_id="new<b>")
        await bot.on_event(old)
        await bot.on_event(new)
        await bot.on_event(Fill(symbol="BTCUSDT", side="BUY", quantity=0.5, executed_price=100.0,
                                client_order_id=f"cli_{new.intent_id}", mode="TESTNET"))
        return _drain(bot)

    [msg] = asyncio.run(run())
    assert "BOT TRADE · BTCUSDT BUY" in msg and "TESTNET ·" in msg and "IST" in msg
    assert "(≈ ₹4,500.00)" in msg            # 0.5 x 100 USD x 90
    assert "$95.0000" in msg                  # stop from the intent this fill belongs to, not the older one
    assert "new&lt;b&gt;" in msg and "new<b>" not in msg   # escaped for Telegram HTML


def test_close_and_halt_messages_are_escaped_and_stamped():
    async def run():
        bot = NotifierBot(EventBus(), mode="PAPER")
        await bot.on_event(PositionClosed(symbol="ETHUSDT", entry_price=10, exit_price=9, quantity=1, pnl_usd=-1.0,
                                          pnl_pct=-10.0, exit_reason="STOP_LOSS"))
        await bot.on_event(SystemAlert(severity="CRITICAL", source="execution_bot", title="Trading halted",
                                       message="HALT: price < stop & spread > 1%"))
        return _drain(bot)

    close, alert = asyncio.run(run())
    assert "POSITION CLOSED · ETHUSDT (STOP_LOSS)" in close and "-$1.00" in close and "PAPER ·" in close
    assert "price &lt; stop &amp; spread &gt; 1%" in alert and "IST" in alert


def test_announce_is_urgent():
    async def run():
        bot = NotifierBot(EventBus())
        await bot.announce("fleet online")
        return bot.outbox_queue.get_nowait()

    msg = asyncio.run(run())
    assert msg.priority == 0 and "fleet online" in msg.text


def test_sender_config_presence_only(tmp_path, monkeypatch):
    for k in notify.KEYS:
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=abc:def\nTELEGRAM_OWNER_CHAT_ID=12345\n", encoding="utf-8")
    assert notify.configured(env) == {"token_set": True, "owner_chat_set": True, "configured": True}
    env.write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    assert notify.configured(env)["configured"] is False


def test_sender_posts_to_owner_chat_and_never_returns_the_token(monkeypatch):
    captured = {}

    class Resp:
        def read(self):
            return json.dumps({"ok": True, "result": {"message_id": 7}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        captured["url"], captured["data"] = req.full_url, req.data.decode()
        return Resp()

    monkeypatch.setattr(notify, "urlopen", fake_urlopen)
    out = notify.send("hi", {"TELEGRAM_BOT_TOKEN": "SECRET:TOKEN", "TELEGRAM_OWNER_CHAT_ID": "42"})
    assert out == {"ok": True, "message_id": 7}
    assert "chat_id=42" in captured["data"] and "SECRET" not in json.dumps(out)
    assert notify.send("hi", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_OWNER_CHAT_ID": "42"})["ok"] is False
