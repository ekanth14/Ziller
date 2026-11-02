"""Common abstract interface and health lifecycle for all autonomous trading bots."""

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Type

from cryptoscope.orchestrator.events import BaseEvent, SystemAlert
from cryptoscope.orchestrator.event_bus import EventBus

logger = logging.getLogger("cryptoscope.orchestrator.base_bot")


class BotStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    STOPPED = "STOPPED"


@dataclass
class BotHealth:
    bot_name: str
    status: BotStatus
    uptime_seconds: float
    last_heartbeat: float
    error_count: int
    events_processed: int
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_alive(self) -> bool:
        return self.status in {BotStatus.HEALTHY, BotStatus.DEGRADED}


class BaseBot(ABC):
    """Abstract base class for isolated micro-bots in the ZILLERS fleet.

    Each bot operates its own event subscriptions, maintains independent state,
    and isolates its task execution so that faults never propagate to peers.
    """

    def __init__(self, name: str, bus: EventBus):
        self.name = name
        self.bus = bus
        self.status = BotStatus.INITIALIZING
        self._start_time = 0.0
        self._last_heartbeat = time.time()
        self.error_count = 0
        self.events_processed = 0
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._subscribed_events: List[Type[BaseEvent]] = []

    def subscribe(self, event_cls: Type[BaseEvent]) -> None:
        """Register subscription for a specific typed event."""
        self._subscribed_events.append(event_cls)
        self.bus.subscribe(event_cls, self._safe_on_event)

    async def _safe_on_event(self, event: BaseEvent) -> None:
        """Execute on_event with fault tracking."""
        if not self._running:
            return
        self.events_processed += 1
        self._last_heartbeat = time.time()
        try:
            await self.on_event(event)
        except Exception as exc:
            self.error_count += 1
            if self.error_count >= 5:
                self.status = BotStatus.CRITICAL
            else:
                self.status = BotStatus.DEGRADED
            logger.error("[%s] Error handling event %s: %s", self.name, event.event_type, exc, exc_info=True)
            await self.emit(SystemAlert(
                severity="ERROR",
                source=self.name,
                title=f"{self.name} Event Handler Error",
                message=str(exc),
                details={"event": event.event_type, "error_count": self.error_count}
            ))

    async def emit(self, event: BaseEvent) -> None:
        """Publish an event to the orchestrator event bus."""
        await self.bus.publish(event)

    async def start(self) -> None:
        """Initialize and launch the bot's background loop."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._last_heartbeat = time.time()
        self.status = BotStatus.HEALTHY
        self._task = asyncio.create_task(self._run_loop(), name=f"bot-{self.name}")
        logger.info("[%s] Started successfully.", self.name)

    async def stop(self) -> None:
        """Cleanly terminate the bot."""
        self._running = False
        self.status = BotStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for evt_cls in self._subscribed_events:
            self.bus.unsubscribe(evt_cls, self._safe_on_event)
        logger.info("[%s] Stopped.", self.name)

    async def _run_loop(self) -> None:
        """Internal worker task loop. Override run() for background polling tasks."""
        try:
            await self.run()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.status = BotStatus.CRITICAL
            self.error_count += 1
            logger.critical("[%s] Worker loop crashed: %s", self.name, exc, exc_info=True)
            await self.emit(SystemAlert(
                severity="CRITICAL",
                source=self.name,
                title=f"{self.name} Loop Crash",
                message=str(exc),
                details={"error_count": self.error_count}
            ))

    async def run(self) -> None:
        """Optional persistent background loop. Default is a simple heartbeat sleep."""
        while self._running:
            self._last_heartbeat = time.time()
            await asyncio.sleep(1.0)

    @abstractmethod
    async def on_event(self, event: BaseEvent) -> None:
        """Event reception hook implemented by concrete micro-bots."""
        pass

    def health(self) -> BotHealth:
        """Return standardized health telemetry."""
        uptime = (time.time() - self._start_time) if self._running else 0.0
        return BotHealth(
            bot_name=self.name,
            status=self.status,
            uptime_seconds=round(uptime, 2),
            last_heartbeat=self._last_heartbeat,
            error_count=self.error_count,
            events_processed=self.events_processed,
            details=self.get_health_details()
        )

    def get_health_details(self) -> Dict[str, Any]:
        """Hook for subclass-specific health metrics."""
        return {}
