"""Unit tests for SupervisorBot fleet management and crash recovery."""

import asyncio
from typing import List

from cryptoscope.orchestrator.events import BaseEvent, SupervisorHeartbeat, SystemAlert
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.base_bot import BaseBot, BotStatus
from cryptoscope.orchestrator.bots.supervisor_bot import SupervisorBot


class CrashProneBot(BaseBot):
    def __init__(self, name: str, bus: EventBus, crash_after: int = 1):
        super().__init__(name, bus)
        self.crash_after = crash_after
        self.cycles = 0

    async def on_event(self, event: BaseEvent) -> None:
        pass

    async def run(self) -> None:
        while self._running:
            self.cycles += 1
            if self.cycles >= self.crash_after:
                self.status = BotStatus.CRITICAL
                raise RuntimeError(f"{self.name} simulation crash!")
            await asyncio.sleep(0.05)


def test_supervisor_registration_and_heartbeat():
    async def _test():
        bus = EventBus()
        supervisor = SupervisorBot(bus, heartbeat_interval=0.1)

        received_heartbeats: List[SupervisorHeartbeat] = []
        async def on_hb(event: SupervisorHeartbeat):
            received_heartbeats.append(event)

        bus.subscribe(SupervisorHeartbeat, on_hb)

        dummy = CrashProneBot("dummy", bus, crash_after=999)
        supervisor.register_bot(dummy)

        await supervisor.start_all()
        await asyncio.sleep(0.25)

        assert len(received_heartbeats) >= 2
        assert "dummy" in received_heartbeats[-1].active_bots

        sys_health = supervisor.get_system_health()
        assert sys_health["status"] == "HEALTHY"
        assert sys_health["managed_bots_count"] == 1

        await supervisor.stop_all()
        await bus.stop()

    asyncio.run(_test())


def test_supervisor_automatic_restart_with_backoff():
    async def _test():
        bus = EventBus()
        supervisor = SupervisorBot(bus, heartbeat_interval=0.05, backoff_base=0.1, max_restarts=3)

        crasher = CrashProneBot("crasher", bus, crash_after=1)
        supervisor.register_bot(crasher)

        alerts: List[SystemAlert] = []
        async def on_alert(event: SystemAlert):
            alerts.append(event)
        bus.subscribe(SystemAlert, on_alert)

        await supervisor.start_all()

        # Allow time for crash -> supervisor detection -> restart
        await asyncio.sleep(0.4)

        # Crasher must have been restarted at least once
        assert supervisor.restart_counts["crasher"] >= 1
        restart_alerts = [a for a in alerts if "Restarting" in a.title]
        assert len(restart_alerts) >= 1

        await supervisor.stop_all()
        await bus.stop()

    asyncio.run(_test())
