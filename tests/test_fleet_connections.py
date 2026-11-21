"""Connections between the Strategy Lab, the strategy library and the bot fleet."""
import asyncio
import json
import math
import random

from cryptoscope.orchestrator.bots.lab_signal_bot import LabSignalBot
from cryptoscope.orchestrator.bots.strategy_bot import StrategyBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import MarketUpdate, Signal, TradeIntent


def _candles(n=250, drift=0.0, seed=3):
    rnd, p, out = random.Random(seed), 100.0, []
    for i in range(n):
        o = p
        p *= math.exp(drift + rnd.gauss(0, 0.004))
        hi, lo = max(o, p) * 1.002, min(o, p) * 0.998
        v = 1000 + rnd.random() * 200
        out.append({"open_time": i * 900_000, "open": o, "high": hi, "low": lo, "close": p, "volume": v,
                    "taker_buy_volume": v * 0.5})
    return out


def _promote(tmp_path, entries):
    path = tmp_path / "promoted.json"
    path.write_text(json.dumps({"promoted": entries}))
    return path


def _run_lab_bot(bot, update):
    out = []

    async def emit(ev):
        out.append(ev)
    bot.emit = emit
    asyncio.run(bot._evaluate(update))
    return out


def test_lab_bot_idle_without_promotions(tmp_path):
    bot = LabSignalBot(EventBus(), promoted_path=tmp_path / "missing.json")
    assert _run_lab_bot(bot, MarketUpdate(symbol="ADAUSDT", price=1.0, candles=_candles())) == []
    assert bot.get_health_details()["state"].startswith("idle")


def test_lab_bot_emits_only_for_matching_symbol_interval_on_fresh_entry(tmp_path, monkeypatch):
    import cryptoscope.desk.strategy_lab as lab
    flips = {"v": [0] * 249 + [1]}
    monkeypatch.setitem(lab.STRATEGIES, "ema_cross", ("EMA cross", "trend", lambda c: flips["v"]))
    path = _promote(tmp_path, [{"symbol": "ADAUSDT", "interval": "15m", "strategy": "ema_cross", "label": "EMA cross",
                                "oos_trades": 120, "dsr_p": 0.01, "pbo": 0.1},
                               {"symbol": "XRPUSDT", "interval": "1d", "strategy": "ema_cross"}])
    bot = LabSignalBot(EventBus(), interval="15m", promoted_path=path)
    c = _candles()
    sigs = _run_lab_bot(bot, MarketUpdate(symbol="ADAUSDT", price=c[-1]["close"], candles=c))
    assert len(sigs) == 1 and sigs[0].direction == "BUY" and sigs[0].strategy_id == "lab:ema_cross"
    assert _run_lab_bot(bot, MarketUpdate(symbol="ADAUSDT", price=1.0, candles=c)) == []      # same bar: once only
    assert _run_lab_bot(bot, MarketUpdate(symbol="XRPUSDT", price=1.0, candles=c)) == []      # promoted on 1d only
    flips["v"] = [0] * 248 + [1, 1]                                                            # already long: no entry
    c2 = c + [dict(c[-1], open_time=c[-1]["open_time"] + 900_000)]
    assert _run_lab_bot(bot, MarketUpdate(symbol="ADAUSDT", price=1.0, candles=c2)) == []
    assert bot.get_health_details()["promoted_for_interval"] == ["ADAUSDT:ema_cross"]


def test_library_strategies_are_lab_candidates_without_lookahead():
    from cryptoscope.desk.strategy_lab import STRATEGIES
    c = _candles(220, drift=0.001)
    for key in ("lib_volume_breakout", "lib_shrink_pullback", "lib_box_oscillation", "lib_vol_compression"):
        assert key in STRATEGIES
        full = STRATEGIES[key][2](c)
        assert len(full) == len(c) and set(full) <= {0, 1}
        cut = STRATEGIES[key][2](c[:180])
        assert full[:180] == cut, key                       # later bars never change earlier positions


def test_strategy_bot_enriches_intent_with_context(tmp_path):
    bot = StrategyBot(EventBus())
    bot.tier_log_path = tmp_path / "tiers.jsonl"
    bot.tier_log_path.write_text(json.dumps({"at": 1, "tiers": {"ADAUSDT": "SHORT_TERM"}}) + "\n")
    c = _candles(250, drift=0.0005)
    out = []

    async def emit(ev):
        out.append(ev)
    bot.emit = emit

    async def go():
        await bot.on_event(MarketUpdate(symbol="ADAUSDT", price=c[-1]["close"], candles=c))
        await bot.on_event(Signal(strategy_id="lab:x", symbol="ADAUSDT", direction="BUY", confidence=0.9,
                                  indicators={"price": c[-1]["close"]}))
    asyncio.run(go())
    intent = next(e for e in out if isinstance(e, TradeIntent))
    f = intent.metadata["features"]
    for k in ("rsi", "r4h", "r24h", "ema_trend", "vpin", "regime"):
        assert k in f, k
    assert f["tier"] == "SHORT_TERM" and 0 <= f["rsi"] <= 100
    assert f["atr_pct"] is not None and f["atr_pct"] < 0.015      # real ATR, not the 1.5% fallback
