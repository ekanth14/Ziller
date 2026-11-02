"""Asynchronous, typed pub/sub event bus with subscriber failure isolation."""

import asyncio
from collections import deque
import inspect
import logging
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Set, Type, TypeVar

from cryptoscope.orchestrator.events import BaseEvent, SystemAlert

logger = logging.getLogger("cryptoscope.orchestrator.bus")

T = TypeVar("T", bound=BaseEvent)
HandlerFunc = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Thread-safe and task-isolated asyncio event bus.

    Ensures that an uncaught exception in any subscriber task does not abort
    event propagation to other subscribers, and preserves a ring buffer of recent events.
    """

    def __init__(self, history_size: int = 1000):
        # event_type_name -> list of async handlers
        self._subscribers: Dict[str, List[HandlerFunc]] = {}
        # Wildcard handlers for all events
        self._wildcard_subscribers: List[HandlerFunc] = []
        self._history: Deque[BaseEvent] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()
        self._running = True

        # Metrics
        self.published_count: int = 0
        self.delivered_count: int = 0
        self.error_count: int = 0

    def subscribe(self, event_cls: Type[BaseEvent], handler: HandlerFunc) -> None:
        """Register an async callback for a specific event class or BaseEvent (all events)."""
        if not inspect.iscoroutinefunction(handler):
            raise TypeError(f"Event handler {handler} must be an async coroutine function")

        key = event_cls.__name__
        if event_cls is BaseEvent:
            if handler not in self._wildcard_subscribers:
                self._wildcard_subscribers.append(handler)
        else:
            handlers = self._subscribers.setdefault(key, [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, event_cls: Type[BaseEvent], handler: HandlerFunc) -> bool:
        """Remove a previously registered callback."""
        if event_cls is BaseEvent:
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)
                return True
            return False

        key = event_cls.__name__
        handlers = self._subscribers.get(key, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to all registered subscribers.

        Each subscriber runs in its own isolated task. A failure in one handler
        never impacts other handlers or crashes the publisher.
        """
        if not self._running:
            return

        self.published_count += 1
        self._history.append(event)

        key = event.event_type
        specific_handlers = self._subscribers.get(key, [])
        all_handlers = list(specific_handlers) + list(self._wildcard_subscribers)

        if not all_handlers:
            return

        tasks = [asyncio.create_task(self._safe_dispatch(handler, event)) for handler in all_handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_dispatch(self, handler: HandlerFunc, event: BaseEvent) -> None:
        """Dispatch event with strict fault isolation."""
        try:
            await handler(event)
            self.delivered_count += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error_count += 1
            handler_name = getattr(handler, "__qualname__", str(handler))
            logger.error("Handler %s crashed while processing %s: %s", handler_name, event.event_type, exc, exc_info=True)

    def get_history(self, event_type: Optional[Type[BaseEvent]] = None, limit: int = 100) -> List[BaseEvent]:
        """Retrieve recent events from the in-memory ring buffer."""
        if event_type is None:
            return list(self._history)[-limit:]
        type_name = event_type.__name__
        matched = [e for e in self._history if e.event_type == type_name]
        return matched[-limit:]

    def clear(self) -> None:
        """Clear subscriptions and history."""
        self._subscribers.clear()
        self._wildcard_subscribers.clear()
        self._history.clear()

    async def stop(self) -> None:
        """Gracefully shut down the bus."""
        self._running = False
