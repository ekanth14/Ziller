"""SupervisorBot: fleet health watchdog, automatic crash recovery with backoff, and heartbeat dispatch."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot, BotHealth, BotStatus
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, SupervisorHeartbeat, SystemAlert

logger = logging.getLogger("cryptoscope.orchestrator.supervisor")


class SupervisorBot(BaseBot):
    """Central supervisor overseeing all micro-bots in the autonomous trading fleet.

    Maintains a watchdog loop that monitors bot health, emits periodic heartbeats,
    and automatically restarts crashed bots with exponential backoff.
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "supervisor",
        heartbeat_interval: float = 3.0,
        max_restarts: int = 5,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ):
        super().__init__(name, bus)
        self.heartbeat_interval = heartbeat_interval
        self.max_restarts = max_restarts
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        # name -> BaseBot
        self.managed_bots: Dict[str, BaseBot] = {}
        # name -> restart count
        self.restart_counts: Dict[str, int] = {}
        # name -> timestamp when restart can be attempted
        self._next_restart_time: Dict[str, float] = {}

    @property
    def bots(self) -> Dict[str, BaseBot]:
        """Convenience accessor for managed micro-bots."""
        return self.managed_bots

    def register_bot(self, bot: BaseBot) -> None:
        """Register a bot under supervisor watchdog control."""
        self.managed_bots[bot.name] = bot
        self.restart_counts[bot.name] = 0

    def unregister_bot(self, bot_name: str) -> Optional[BaseBot]:
        """Unregister a bot from supervisor control."""
        self.restart_counts.pop(bot_name, None)
        self._next_restart_time.pop(bot_name, None)
        return self.managed_bots.pop(bot_name, None)

    async def start_all(self) -> None:
        """Start all managed bots and the supervisor itself."""
        await self.start()
        for bot in self.managed_bots.values():
            await bot.start()

    async def stop_all(self) -> None:
        """Stop all managed bots cleanly."""
        for bot in self.managed_bots.values():
            await bot.stop()
        await self.stop()

    async def on_event(self, event: BaseEvent) -> None:
        """Listen for alert events or commands."""
        pass

    async def run(self) -> None:
        """Persistent supervisor watchdog loop."""
        while self._running:
            now = time.time()
            self._last_heartbeat = now
            active = []
            degraded = []
            unhealthy = []

            for name, bot in list(self.managed_bots.items()):
                h = bot.health()

                # Check if bot has crashed or failed
                is_failed = (
                    h.status in {BotStatus.CRITICAL, BotStatus.STOPPED} or
                    (bot._task is not None and bot._task.done() and not bot._task.cancelled())
                )

                if is_failed:
                    unhealthy.append(name)
                    await self._handle_bot_failure(bot, now)
                elif h.status == BotStatus.DEGRADED:
                    degraded.append(name)
                else:
                    active.append(name)

            # Emit fleet liveness heartbeat
            uptime = now - self._start_time if self._running else 0.0
            await self.emit(SupervisorHeartbeat(
                supervisor_id=self.name,
                active_bots=active,
                degraded_bots=degraded,
                unhealthy_bots=unhealthy,
                system_uptime_seconds=round(uptime, 2)
            ))

            await asyncio.sleep(self.heartbeat_interval)

    async def _handle_bot_failure(self, bot: BaseBot, now: float) -> None:
        """Schedule and execute bot restart with exponential backoff."""
        name = bot.name
        can_restart_at = self._next_restart_time.get(name, 0.0)

        if now < can_restart_at:
            return  # Still in backoff window

        current_restarts = self.restart_counts.get(name, 0)

        if current_restarts >= self.max_restarts:
            logger.critical("[%s] Bot '%s' exceeded max restarts (%d). Halting restart attempts.", self.name, name, self.max_restarts)
            await self.emit(SystemAlert(
                severity="CRITICAL",
                source=self.name,
                title=f"Bot '{name}' Unrecoverable",
                message=f"Exceeded max restart limit ({self.max_restarts}). Manual operator intervention required.",
                details={"bot": name, "restarts": current_restarts}
            ))
            return

        # Compute exponential backoff: base * 2^(restarts)
        backoff = min(self.backoff_base * (2 ** current_restarts), self.backoff_max)
        self.restart_counts[name] = current_restarts + 1
        self._next_restart_time[name] = now + backoff

        logger.warning("[%s] Bot '%s' crashed! Restart #%d scheduled after %.1fs backoff.", self.name, name, self.restart_counts[name], backoff)
        await self.emit(SystemAlert(
            severity="WARNING",
            source=self.name,
            title=f"Restarting Bot '{name}'",
            message=f"Bot crashed; initiating restart #{self.restart_counts[name]} with {backoff:.1f}s backoff.",
            details={"bot": name, "restart_attempt": self.restart_counts[name], "backoff_sec": backoff}
        ))

        # Perform asynchronous restart
        asyncio.create_task(self._restart_bot(bot, backoff))

    async def _restart_bot(self, bot: BaseBot, delay: float) -> None:
        """Perform the actual restart after delay."""
        await asyncio.sleep(delay)
        try:
            await bot.stop()
            bot.error_count = 0
            await bot.start()
            logger.info("[%s] Bot '%s' successfully restarted and healthy.", self.name, bot.name)
            await self.emit(SystemAlert(
                severity="INFO",
                source=self.name,
                title=f"Bot '{bot.name}' Recovered",
                message=f"Bot restarted successfully and restored to HEALTHY status."
            ))
        except Exception as exc:
            logger.error("[%s] Failed to restart bot '%s': %s", self.name, bot.name, exc, exc_info=True)

    def get_system_health(self) -> Dict[str, Any]:
        """Aggregate health telemetry across the entire fleet."""
        uptime = (time.time() - self._start_time) if self._running else 0.0
        bot_healths = {name: bot.health().__dict__ for name, bot in self.managed_bots.items()}
        healthy_count = sum(1 for bot in self.managed_bots.values() if bot.health().is_alive)
        all_alive = all(bot.health().is_alive for bot in self.managed_bots.values())
        return {
            "supervisor": self.name,
            "status": "HEALTHY" if all_alive else "DEGRADED",
            "uptime_seconds": round(uptime, 2),
            "managed_bots_count": len(self.managed_bots),
            "total_bots_count": len(self.managed_bots),
            "healthy_bots_count": healthy_count,
            "bots": bot_healths,
            "restarts": dict(self.restart_counts)
        }

    def health_report(self) -> Dict[str, Any]:
        """Convenience alias for get_system_health."""
        return self.get_system_health()
