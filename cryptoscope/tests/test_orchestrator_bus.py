"""Unit tests for the ZILLERS asyncio event bus and BaseBot lifecycle."""

import asyncio
from typing import List

from cryptoscope.orchestrator.events import (
    BaseEvent,
    MarketUpdate,
    Signal,
    TradeIntent,
    DebateResult,
    RiskDecision,
    OrderRequest,
    Fill,
    PositionClosed,
    SystemAlert,
    SupervisorHeartbeat,
)
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.base_bot import BaseBot, BotStatus


class MockReceiverBot(BaseBot):
    def __init__(self, name: str, bus: EventBus):
        super().__init__(name, bus)
        self.received_updates: List[MarketUpdate] = []
        self.received_alerts: List[SystemAlert] = []

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            self.received_updates.append(event)
        elif isinstance(event, SystemAlert):
            self.received_alerts.append(event)


class FailingBot(BaseBot):
    async def on_event(self, event: BaseEvent) -> None:
        raise RuntimeError("Deliberate bot failure for isolation test")


def test_event_serialization():
    mu = MarketUpdate(symbol="BTCUSDT", price=78500.0, bid=78495.0, ask=78505.0)
    d = mu.to_dict()
    assert d["symbol"] == "BTCUSDT"
    assert d["price"] == 78500.0
    assert mu.event_type == "MarketUpdate"


def test_event_bus_pub_sub():
    async def _test():
        bus = EventBus()
        bot = MockReceiverBot("receiver-1", bus)
        bot.subscribe(MarketUpdate)
        await bot.start()

        mu = MarketUpdate(symbol="ETHUSDT", price=2300.0)
        await bus.publish(mu)

        assert len(bot.received_updates) == 1
        assert bot.received_updates[0].symbol == "ETHUSDT"
        assert bot.health().events_processed == 1

        await bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_subscriber_fault_isolation():
    async def _test():
        bus = EventBus()
        receiver = MockReceiverBot("receiver-ok", bus)
        failing = FailingBot("failing-bot", bus)

        receiver.subscribe(MarketUpdate)
        failing.subscribe(MarketUpdate)

        await receiver.start()
        await failing.start()

        mu = MarketUpdate(symbol="SOLUSDT", price=95.0)
        await bus.publish(mu)

        # Receiver still received the event
        assert len(receiver.received_updates) == 1
        assert receiver.received_updates[0].symbol == "SOLUSDT"

        # Failing bot degraded and error was recorded
        assert failing.error_count == 1
        assert failing.status == BotStatus.DEGRADED

        await receiver.stop()
        await failing.stop()
        await bus.stop()

    asyncio.run(_test())


def test_event_history_ring_buffer():
    async def _test():
        bus = EventBus(history_size=5)
        for i in range(10):
            await bus.publish(MarketUpdate(symbol=f"SYM{i}", price=float(i)))

        history = bus.get_history()
        assert len(history) == 5
        assert history[-1].symbol == "SYM9"
        await bus.stop()

    asyncio.run(_test())
