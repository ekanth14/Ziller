"""Unit tests for RiskBot deterministic safety controls and sizing."""

import asyncio
from typing import List

from cryptoscope.orchestrator.events import (
    DebateResult,
    Fill,
    PositionClosed,
    RiskDecision,
    TradeIntent,
)
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.bots.risk_bot import RiskBot


def test_risk_bot_approves_valid_trade():
    async def _test():
        bus = EventBus()
        risk_bot = RiskBot(bus, initial_nav=10000.0)
        await risk_bot.start()

        decisions: List[RiskDecision] = []
        async def on_decision(event: RiskDecision):
            decisions.append(event)
        bus.subscribe(RiskDecision, on_decision)

        intent = TradeIntent(
            intent_id="intent_101",
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=70000.0,
            stop_loss=68500.0,  # ~2.1% stop distance
            take_profit=73000.0
        )
        await bus.publish(intent)

        debate = DebateResult(
            intent_id="intent_101",
            symbol="BTCUSDT",
            conviction_score=35.0,
            verdict="APPROVE"
        )
        await bus.publish(debate)
        await asyncio.sleep(0.05)

        assert len(decisions) == 1
        d = decisions[0]
        assert d.decision == "APPROVED"
        assert d.approved_quantity > 0.0
        assert d.position_size_usd > 0.0
        assert len(d.veto_reasons) == 0

        await risk_bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_risk_bot_vetoes_unapproved_debate():
    async def _test():
        bus = EventBus()
        risk_bot = RiskBot(bus)
        await risk_bot.start()

        decisions: List[RiskDecision] = []
        async def on_decision(event: RiskDecision):
            decisions.append(event)
        bus.subscribe(RiskDecision, on_decision)

        intent = TradeIntent(
            intent_id="intent_102",
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=70000.0,
            stop_loss=68000.0,
            take_profit=74000.0
        )
        await bus.publish(intent)

        debate = DebateResult(
            intent_id="intent_102",
            symbol="BTCUSDT",
            conviction_score=-15.0,
            verdict="REJECT"
        )
        await bus.publish(debate)
        await asyncio.sleep(0.05)

        assert len(decisions) == 1
        d = decisions[0]
        assert d.decision == "VETOED"
        assert any("Debate layer verdict is REJECT" in r for r in d.veto_reasons)

        await risk_bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_risk_bot_daily_loss_limit_veto():
    async def _test():
        bus = EventBus()
        # $10,000 NAV, 3% daily loss limit = $300 max loss
        risk_bot = RiskBot(bus, initial_nav=10000.0, max_daily_loss_pct=0.03)
        await risk_bot.start()

        # Simulate earlier realized loss of -$350
        await bus.publish(PositionClosed(
            symbol="SOLUSDT",
            side="BUY",
            entry_price=100.0,
            exit_price=96.5,
            quantity=100.0,
            pnl_usd=-350.0,
            pnl_pct=-3.5,
            exit_reason="STOP_LOSS"
        ))
        await asyncio.sleep(0.02)

        decisions: List[RiskDecision] = []
        async def on_decision(event: RiskDecision):
            decisions.append(event)
        bus.subscribe(RiskDecision, on_decision)

        intent = TradeIntent(
            intent_id="intent_103",
            symbol="BTCUSDT",
            direction="BUY",
            entry_price=70000.0,
            stop_loss=68500.0,
            take_profit=73000.0
        )
        await bus.publish(intent)
        await bus.publish(DebateResult(intent_id="intent_103", symbol="BTCUSDT", verdict="APPROVE"))
        await asyncio.sleep(0.05)

        assert len(decisions) == 1
        d = decisions[0]
        assert d.decision == "VETOED"
        assert any("DAILY_LOSS_LIMIT" in r for r in d.veto_reasons)

        await risk_bot.stop()
        await bus.stop()

    asyncio.run(_test())


def test_risk_bot_correlation_cap_veto():
    async def _test():
        bus = EventBus()
        risk_bot = RiskBot(bus, correlation_cap=0.85)
        await risk_bot.start()

        # Existing open BTC position
        await bus.publish(Fill(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.05,
            executed_price=70000.0
        ))
        await asyncio.sleep(0.02)

        decisions: List[RiskDecision] = []
        async def on_decision(event: RiskDecision):
            decisions.append(event)
        bus.subscribe(RiskDecision, on_decision)

        # Propose ETH trade (ETH and BTC have 0.88 correlation > 0.85 cap)
        intent = TradeIntent(
            intent_id="intent_104",
            symbol="ETHUSDT",
            direction="BUY",
            entry_price=2300.0,
            stop_loss=2250.0,
            take_profit=2400.0
        )
        await bus.publish(intent)
        await bus.publish(DebateResult(intent_id="intent_104", symbol="ETHUSDT", verdict="APPROVE"))
        await asyncio.sleep(0.05)

        assert len(decisions) == 1
        d = decisions[0]
        assert d.decision == "VETOED"
        assert any("CORRELATION_CAP" in r for r in d.veto_reasons)

        await risk_bot.stop()
        await bus.stop()

    asyncio.run(_test())
