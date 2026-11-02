"""Unit tests for ExecutionBot order routing, stop losses, watchdog, and state persistence."""

import asyncio
from pathlib import Path
import tempfile
import time
from typing import List

from cryptoscope.orchestrator.events import (
    Fill,
    MarketUpdate,
    OrderRequest,
    PositionClosed,
    RiskDecision,
    SupervisorHeartbeat,
    SystemAlert,
    TradeIntent,
)
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot


def test_execution_bot_places_order_and_stop_loss():
    async def _test():
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test_exec_state.db")
            bus = EventBus()
            exec_bot = ExecutionBot(bus, mode="PAPER", db_path=db_path)
            await exec_bot.start()

            orders: List[OrderRequest] = []
            fills: List[Fill] = []
            async def on_order(event: OrderRequest):
                orders.append(event)
            async def on_fill(event: Fill):
                fills.append(event)

            bus.subscribe(OrderRequest, on_order)
            bus.subscribe(Fill, on_fill)

            intent = TradeIntent(
                intent_id="intent_exec_1",
                symbol="BTCUSDT",
                direction="BUY",
                entry_price=70000.0,
                stop_loss=68500.0,
                take_profit=73000.0
            )
            await bus.publish(intent)

            risk = RiskDecision(
                intent_id="intent_exec_1",
                symbol="BTCUSDT",
                decision="APPROVED",
                approved_quantity=0.05,
                position_size_usd=3500.0,
                stop_distance_pct=2.14
            )
            await bus.publish(risk)
            await asyncio.sleep(0.05)

            # Order and fill emitted
            assert len(orders) == 1
            assert orders[0].symbol == "BTCUSDT"
            assert orders[0].quantity == 0.05

            assert len(fills) == 1
            assert fills[0].symbol == "BTCUSDT"
            assert fills[0].quantity == 0.05
            assert fills[0].stop_order_id is not None  # Exchange-level stop placed

            # Position tracked in memory and persisted
            assert "BTCUSDT" in exec_bot.active_positions
            pos = exec_bot.active_positions["BTCUSDT"]
            assert pos["stop_price"] == 68500.0
            assert pos["target_price"] == 73000.0

            # Test position exit when price drops to stop loss
            closed_events: List[PositionClosed] = []
            async def on_closed(event: PositionClosed):
                closed_events.append(event)
            bus.subscribe(PositionClosed, on_closed)

            mu_stop = MarketUpdate(symbol="BTCUSDT", price=68400.0)  # Below 68500 stop
            await bus.publish(mu_stop)
            await asyncio.sleep(0.05)

            assert len(closed_events) == 1
            c = closed_events[0]
            assert c.exit_reason == "STOP_LOSS"
            assert c.pnl_usd < 0.0
            assert "BTCUSDT" not in exec_bot.active_positions

            await exec_bot.stop()
            await bus.stop()

    asyncio.run(_test())


def test_supervisor_heartbeat_loss_triggers_emergency_protection():
    async def _test():
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "test_exec_watchdog.db")
            bus = EventBus()
            # Fast 0.1s supervisor timeout for test
            exec_bot = ExecutionBot(bus, mode="PAPER", db_path=db_path, supervisor_timeout_sec=0.1)
            await exec_bot.start()

            alerts: List[SystemAlert] = []
            async def on_alert(event: SystemAlert):
                alerts.append(event)
            bus.subscribe(SystemAlert, on_alert)

            # Manually inject an active position
            exec_bot.active_positions["SOLUSDT"] = {
                "symbol": "SOLUSDT",
                "side": "BUY",
                "quantity": 10.0,
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 110.0
            }

            # Allow watchdog loop to run without supervisor heartbeat
            await asyncio.sleep(0.25)

            # Emergency protection must be active
            assert exec_bot.emergency_protection_active is True
            assert len(alerts) >= 1
            assert "Emergency Protection" in alerts[0].title
            # Stop tightened to break-even entry price
            assert exec_bot.active_positions["SOLUSDT"]["stop_price"] == 100.0

            # Restoration test: supervisor sends heartbeat
            await bus.publish(SupervisorHeartbeat())
            await asyncio.sleep(0.05)
            assert exec_bot.emergency_protection_active is False

            await exec_bot.stop()
            await bus.stop()

    asyncio.run(_test())
