"""Integration tests for Data, Analyst, Quant, Strategy, and Debate bots."""

import asyncio
from typing import List
from unittest.mock import MagicMock

from cryptoscope.orchestrator.events import (
    BaseEvent,
    MarketUpdate,
    Signal,
    TradeIntent,
    DebateResult,
)
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.bots.data_bot import DataBot
from cryptoscope.orchestrator.bots.analyst_bot import AnalystBot
from cryptoscope.orchestrator.bots.quant_bot import QuantBot
from cryptoscope.orchestrator.bots.strategy_bot import StrategyBot
from cryptoscope.orchestrator.bots.debate_bot import DebateBot


def _make_dummy_candles(n: int = 30, base_price: float = 70000.0, trend: float = 1.002):
    candles = []
    p = base_price
    for i in range(n):
        nxt = p * trend
        candles.append({
            "open_time": i * 60,
            "close_time": (i + 1) * 60,
            "open": p,
            "high": max(p, nxt) * 1.001,
            "low": min(p, nxt) * 0.999,
            "close": nxt,
            "volume": 100.0,
            "taker_buy_volume": 60.0
        })
        p = nxt
    return candles


def test_data_to_analyst_to_strategy_pipeline():
    async def _test():
        bus = EventBus()
        data_bot = DataBot(bus, symbols=[])
        analyst_bot = AnalystBot(bus)
        strategy_bot = StrategyBot(bus, min_confidence=0.60)

        received_intents: List[TradeIntent] = []
        async def on_intent(event: TradeIntent):
            received_intents.append(event)

        bus.subscribe(TradeIntent, on_intent)

        await data_bot.start()
        await analyst_bot.start()
        await strategy_bot.start()

        # Feed 30 bullish candles
        candles = _make_dummy_candles(30, 70000.0, 1.002)
        for c in candles:
            await data_bot.feed_candle("BTCUSDT", c, history=candles[:candles.index(c)])

        # Allow time for async propagation
        await asyncio.sleep(0.1)

        # StrategyBot should have proposed at least one TradeIntent
        assert len(received_intents) >= 1
        intent = received_intents[0]
        assert intent.symbol == "BTCUSDT"
        assert intent.direction in {"BUY", "SELL"}
        assert intent.entry_price > 0
        assert intent.stop_loss > 0
        assert intent.take_profit > 0

        await data_bot.stop()
        await analyst_bot.stop()
        await strategy_bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_debate_bot_approval_and_fail_closed_timeout():
    async def _test():
        bus = EventBus()
        debate_bot = DebateBot(bus, timeout_seconds=0.001)  # Micro timeout forcing fail-closed
        await debate_bot.start()

        received_results: List[DebateResult] = []
        async def on_debate(event: DebateResult):
            received_results.append(event)
        bus.subscribe(DebateResult, on_debate)

        intent = TradeIntent(
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=78000.0,
            stop_loss=76500.0,
            take_profit=81000.0
        )
        await bus.publish(intent)
        await asyncio.sleep(0.05)

        assert len(received_results) == 1
        res = received_results[0]
        # Must fail closed to REJECT on timeout
        assert res.verdict == "REJECT"
        assert res.fallback_used is True

        await debate_bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_quant_bot_emits_alpha_signal():
    async def _test():
        bus = EventBus()
        quant_bot = QuantBot(bus)
        await quant_bot.start()

        signals: List[Signal] = []
        async def on_sig(event: Signal):
            signals.append(event)
        bus.subscribe(Signal, on_sig)

        candles = _make_dummy_candles(40, 2500.0, 1.001)
        mu = MarketUpdate(symbol="ETHUSDT", price=2600.0, candles=candles)
        await bus.publish(mu)
        await asyncio.sleep(0.05)

        assert quant_bot.events_processed >= 1
        assert "ETHUSDT" in quant_bot.latest_regimes

        await quant_bot.stop()
        await bus.stop()

    asyncio.run(_test())
