"""NotifierBot: Rich alert formatting, rate-limiting, and offline-resilient dispatching."""

import asyncio
from collections import deque
import logging
import time
from typing import Any, Callable, Deque, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    BaseEvent,
    DebateResult,
    Fill,
    PositionClosed,
    RiskDecision,
    SystemAlert,
    TradeIntent,
)

logger = logging.getLogger("cryptoscope.orchestrator.notifier_bot")


class NotificationMessage:
    def __init__(self, text: str, category: str, priority: int = 1, timestamp: Optional[float] = None):
        self.text = text
        self.category = category  # 'ENTRY', 'EXIT', 'ALERT', 'REPORT'
        self.priority = priority  # 0=URGENT (bypasses batching), 1=NORMAL, 2=LOW
        self.timestamp = timestamp or time.time()
        self.delivered = False


class NotifierBot(BaseBot):
    """Formats institutional trading notifications with rate-limiting and offline buffering."""

    def __init__(
        self,
        bus: EventBus,
        name: str = "notifier_bot",
        max_queue_size: int = 1000,
        rate_limit_per_minute: int = 30,
        dispatch_callback: Optional[Callable[[str], Any]] = None
    ):
        super().__init__(name, bus)
        self.max_queue_size = max_queue_size
        self.rate_limit_per_minute = rate_limit_per_minute
        self.dispatch_callback = dispatch_callback

        # Offline & rate-limiting queue
        self.outbox_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.delivery_history: Deque[float] = deque()
        self.offline_spool: List[NotificationMessage] = []

        # Context caches to correlate fills with debates and intents
        self._intents: Dict[str, TradeIntent] = {}
        self._debates: Dict[str, DebateResult] = {}
        self._risks: Dict[str, RiskDecision] = {}

        self.subscribe(TradeIntent)
        self.subscribe(DebateResult)
        self.subscribe(RiskDecision)
        self.subscribe(Fill)
        self.subscribe(PositionClosed)
        self.subscribe(SystemAlert)

    async def on_event(self, event: BaseEvent) -> None:
        """Process incoming bus events and format notifications."""
        if isinstance(event, TradeIntent):
            self._intents[event.intent_id] = event
        elif isinstance(event, DebateResult):
            self._debates[event.intent_id] = event
        elif isinstance(event, RiskDecision):
            self._risks[event.intent_id] = event
        elif isinstance(event, Fill):
            await self._handle_fill(event)
        elif isinstance(event, PositionClosed):
            await self._handle_position_closed(event)
        elif isinstance(event, SystemAlert):
            await self._handle_system_alert(event)

    async def _handle_fill(self, fill: Fill) -> None:
        """Format and enqueue a detailed entry alert."""
        # Find matching intent and debate
        intent = None
        debate = None
        for i_id, i_val in self._intents.items():
            if i_val.symbol == fill.symbol:
                intent = i_val
                debate = self._debates.get(i_id)
                break

        price = getattr(fill, "executed_price", getattr(fill, "fill_price", 0.0))
        fee = getattr(fill, "fee", getattr(fill, "fee_usd", 0.0))
        slippage = getattr(fill, "slippage_pct", 0.0)

        side_emoji = "🟢" if fill.side == "BUY" else "🔴"
        title = f"{side_emoji} <b>EXECUTION ENTRY: {fill.symbol} ({fill.side})</b>"
        
        lines = [
            title,
            "━━━━━━━━━━━━━━━━━━━",
            f"<b>Filled Price:</b> ${price:,.4f}",
            f"<b>Quantity:</b> {fill.quantity} (${fill.quantity * price:,.2f})",
            f"<b>Exchange Fee:</b> ${fee:.2f} | <b>Slippage:</b> {slippage:.3f}%"
        ]

        if intent:
            lines.extend([
                f"🛡️ <b>Stop Loss:</b> ${intent.stop_loss:,.4f} [Exchange Gated]",
                f"🎯 <b>Take Profit:</b> ${intent.take_profit:,.4f}",
                f"🏷️ <b>Strategy:</b> {getattr(intent, 'strategy_id', 'core')}"
            ])

        if debate:
            score = getattr(debate, 'conviction_score', 0.0)
            summary = getattr(debate, 'bull_thesis', '') or getattr(debate, 'debate_summary', '')
            lines.extend([
                f"⚖️ <b>Consensus:</b> {debate.verdict} ({score:+.1f} conviction)",
                f"💬 <b>Debate:</b> {summary}"
            ])

        lines.append("━━━━━━━━━━━━━━━━━━━")
        msg = NotificationMessage(text="\n".join(lines), category="ENTRY", priority=0)
        await self.enqueue_notification(msg)

    async def _handle_position_closed(self, closed: PositionClosed) -> None:
        """Format and enqueue a position closure alert."""
        pnl_emoji = "🟢" if closed.pnl_usd >= 0 else "🔴"
        icon = "🎯" if closed.exit_reason == "TAKE_PROFIT" else "🛑"
        title = f"{icon} <b>POSITION CLOSED: {closed.symbol} ({closed.exit_reason})</b>"

        mins = int(closed.duration_seconds // 60)
        secs = int(closed.duration_seconds % 60)
        duration_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        pnl_str = f"+${closed.pnl_usd:,.2f}" if closed.pnl_usd >= 0 else f"-${abs(closed.pnl_usd):,.2f}"
        pct_str = f"+{closed.pnl_pct:.2f}%" if closed.pnl_pct >= 0 else f"{closed.pnl_pct:.2f}%"

        lines = [
            title,
            "━━━━━━━━━━━━━━━━━━━",
            f"<b>Entry Price:</b> ${closed.entry_price:,.4f}",
            f"<b>Exit Price:</b> ${closed.exit_price:,.4f}",
            f"<b>Quantity:</b> {closed.quantity}",
            f"{pnl_emoji} <b>Realized PnL:</b> {pnl_str} ({pct_str})",
            f"⏱️ <b>Hold Time:</b> {duration_str}",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        msg = NotificationMessage(text="\n".join(lines), category="EXIT", priority=0)
        await self.enqueue_notification(msg)

    async def _handle_system_alert(self, alert: SystemAlert) -> None:
        """Format and enqueue critical system diagnostics."""
        sev = alert.severity.upper()
        icon = "🚨" if sev == "CRITICAL" else ("⚠️" if sev == "ERROR" else "ℹ️")
        priority = 0 if sev in {"CRITICAL", "ERROR"} else 2

        lines = [
            f"{icon} <b>SYSTEM ALERT [{sev}]</b>",
            f"<b>Source:</b> {alert.source}",
            f"<b>Title:</b> {alert.title}",
            f"<b>Message:</b> {alert.message}"
        ]
        msg = NotificationMessage(text="\n".join(lines), category="ALERT", priority=priority)
        await self.enqueue_notification(msg)

    async def enqueue_notification(self, msg: NotificationMessage) -> None:
        """Place notification in queue with overflow fallback to offline spool."""
        try:
            self.outbox_queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("[%s] Outbox queue full (%d). Spooling offline.", self.name, self.max_queue_size)
            if len(self.offline_spool) < 2000:
                self.offline_spool.append(msg)

    def is_rate_limited(self) -> bool:
        """Check if message dispatch rate limit is exceeded."""
        now = time.time()
        one_min_ago = now - 60.0
        while self.delivery_history and self.delivery_history[0] < one_min_ago:
            self.delivery_history.popleft()
        return len(self.delivery_history) >= self.rate_limit_per_minute

    async def run(self) -> None:
        """Dispatch loop consuming the notification outbox with rate-limiting."""
        while self._running:
            self._last_heartbeat = time.time()
            try:
                # Wait up to 1 second for next message
                msg: NotificationMessage = await asyncio.wait_for(self.outbox_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Re-queue offline spool if outbox has room
                if self.offline_spool and not self.outbox_queue.full():
                    spooled = self.offline_spool.pop(0)
                    await self.outbox_queue.put(spooled)
                continue

            # Respect rate limit unless URGENT priority (priority 0)
            if msg.priority > 0 and self.is_rate_limited():
                await asyncio.sleep(1.0)

            # Dispatch via callback if registered
            if self.dispatch_callback:
                try:
                    res = self.dispatch_callback(msg.text)
                    if asyncio.iscoroutine(res):
                        await res
                    msg.delivered = True
                    self.delivery_history.append(time.time())
                except Exception as exc:
                    logger.warning("[%s] Dispatch callback failed (Telegram offline?): %s. Spooling.", self.name, exc)
                    if len(self.offline_spool) < 2000:
                        self.offline_spool.append(msg)
            else:
                msg.delivered = True
                self.delivery_history.append(time.time())

            self.outbox_queue.task_done()
