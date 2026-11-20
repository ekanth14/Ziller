"""Bar-VPIN, volatility regime and the risk-only size multiplier."""
import asyncio
import math
import random

from cryptoscope.quant.flow_risk import (book_imbalance, size_multiplier, vol_regime, vpin_series, vpin_state)


def _bars(n, buy_share=0.5, vol=0.002, seed=1, tail=None):
    rnd, p, out = random.Random(seed), 100.0, []
    for i in range(n):
        share, sd = buy_share, vol
        if tail and i >= n - tail[0]:
            share, sd = tail[1], tail[2]
        p *= math.exp(rnd.gauss(0, sd))
        v = 1000.0
        out.append({"close": p, "volume": v, "taker_buy_volume": v * min(1, max(0, share + rnd.gauss(0, 0.03)))})
    return out


def test_vpin_flags_one_sided_flow_relative_to_own_history():
    calm = vpin_state(_bars(60))
    assert calm["vpin"] is not None and not calm["toxic"]
    toxic = vpin_state(_bars(60, tail=(8, 0.95, 0.002)))      # last 8 bars: 95% taker buys
    assert toxic["toxic"] and toxic["vpin"] > calm["vpin"]
    assert vpin_series([{"volume": 0, "taker_buy_volume": 0}] * 30) == []
    assert vpin_state([{"close": 1}])["vpin"] is None          # no taker split -> unknown, not toxic


def test_vol_regime_and_multiplier_only_shrink():
    assert vol_regime(_bars(60))["regime"] == "NORMAL"
    assert vol_regime(_bars(60, tail=(20, 0.5, 0.012)))["regime"] in {"HIGH_VOL", "EXTREME_VOL"}
    assert vol_regime(_bars(10))["regime"] is None
    assert size_multiplier({})["multiplier"] == 1.0
    assert size_multiplier({"vpin_toxic": True})["multiplier"] == 0.5
    assert size_multiplier({"regime": "EXTREME_VOL", "vpin_toxic": True})["multiplier"] == 0.25
    assert size_multiplier({"regime": "HIGH_VOL"})["multiplier"] == 0.5


def test_book_imbalance():
    d = {"bids": [["99.9", "30"]], "asks": [["100.1", "10"], ["101.0", "999"]]}   # far ask outside 0.5%
    assert abs(book_imbalance(d) - 0.5) < 0.01
    assert book_imbalance({"bids": [], "asks": []}) is None


def test_risk_bot_shrinks_size_in_extreme_regime():
    from cryptoscope.orchestrator.bots.risk_bot import RiskBot
    from cryptoscope.orchestrator.event_bus import EventBus
    from cryptoscope.orchestrator.events import DebateResult, RiskDecision, TradeIntent

    async def size(features):
        bot = RiskBot(EventBus(), initial_nav=10_000)
        it = TradeIntent(symbol="ADAUSDT", direction="BUY", entry_price=1.0, stop_loss=0.99, take_profit=1.01,
                         metadata={"features": features})
        bot.cached_intents[it.intent_id] = it
        out = []

        async def emit(ev):
            out.append(ev)
        bot.emit = emit
        await bot._evaluate_risk(DebateResult(intent_id=it.intent_id, symbol="ADAUSDT", verdict="APPROVE",
                                              conviction_score=8))
        return next(e for e in out if isinstance(e, RiskDecision)).position_size_usd

    normal, extreme = asyncio.run(size({})), asyncio.run(size({"regime": "EXTREME_VOL"}))
    assert normal > 0 and abs(extreme - normal * 0.25) < 0.05
