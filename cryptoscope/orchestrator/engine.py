"""OrchestratorEngine: Master coordinator orchestrating the 10 micro-bots of ZILLERS."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.bots import (
    SupervisorBot,
    DataBot,
    AnalystBot,
    QuantBot,
    StrategyBot,
    DebateBot,
    RiskBot,
    ExecutionBot,
    JournalBot,
    NotifierBot,
)
from cryptoscope.telegram.gateway import TelegramGateway

logger = logging.getLogger("cryptoscope.orchestrator.engine")


class OrchestratorEngine:
    """Institutional coordinator orchestrating the 10 micro-bots over the EventBus."""

    def __init__(
        self,
        mode: str = "PAPER",  # 'OBSERVE', 'PAPER', 'TESTNET', 'LIVE'
        work_dir: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        telegram_token: Optional[str] = None,
        telegram_owner_chat_id: Optional[int | str] = None,
    ):
        self.mode = mode.upper()
        self.work_dir = Path(work_dir or "work/runtime")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        self.bus = EventBus()
        self.supervisor = SupervisorBot(self.bus)

        # Micro-bots
        self.data_bot = DataBot(self.bus, symbols=self.symbols)
        self.analyst_bot = AnalystBot(self.bus)
        self.quant_bot = QuantBot(self.bus)
        self.strategy_bot = StrategyBot(self.bus)
        self.debate_bot = DebateBot(self.bus)
        self.risk_bot = RiskBot(
            self.bus,
            initial_nav=10000.0,
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10
        )
        self.execution_bot = ExecutionBot(
            self.bus,
            mode=self.mode,
            db_path=str(self.work_dir / "orchestrator_execution.db")
        )
        self.journal_bot = JournalBot(
            self.bus,
            db_path=str(self.work_dir / "trading_journal.db")
        )
        self.notifier_bot = NotifierBot(
            self.bus,
            rate_limit_per_minute=30
        )

        # Register bots with supervisor watchdog
        for bot in [
            self.data_bot,
            self.analyst_bot,
            self.quant_bot,
            self.strategy_bot,
            self.debate_bot,
            self.risk_bot,
            self.execution_bot,
            self.journal_bot,
            self.notifier_bot,
        ]:
            self.supervisor.register_bot(bot)

        # Optional Telegram Gateway
        self.telegram = TelegramGateway(
            token=telegram_token,
            owner_chat_id=telegram_owner_chat_id,
            supervisor=self.supervisor,
            strategy_bot=self.strategy_bot,
            risk_bot=self.risk_bot,
            execution_bot=self.execution_bot,
            journal_bot=self.journal_bot,
            notifier_bot=self.notifier_bot
        )
        # Link notifier callback to telegram gateway if configured
        if self.telegram.token and self.telegram.owner_chat_id:
            self.notifier_bot.dispatch_callback = self.telegram.send_alert

        self._running = False

    async def start(self) -> None:
        """Launch the entire autonomous fleet."""
        if self._running:
            return
        logger.info("[OrchestratorEngine] Starting autonomous fleet in %s mode...", self.mode)
        self._running = True

        # Start supervisor first
        await self.supervisor.start()

        # Start all registered bots
        for bot in self.supervisor.bots.values():
            await bot.start()

        # Build telegram if token provided
        app = self.telegram.build_application()
        if app:
            try:
                await app.initialize()
                await app.start()
                logger.info("[OrchestratorEngine] Telegram Gateway active for owner %s", self.telegram.owner_chat_id)
            except Exception as exc:
                logger.warning("[OrchestratorEngine] Telegram could not connect: %s. Offline spool enabled.", exc)

        logger.info("[OrchestratorEngine] Autonomous fleet online (%d bots active).", len(self.supervisor.bots))

    async def stop(self) -> None:
        """Clean shutdown of all bots, bus, and gateways."""
        if not self._running:
            return
        logger.info("[OrchestratorEngine] Stopping autonomous fleet...")
        self._running = False

        if self.telegram.app:
            try:
                await self.telegram.app.stop()
                await self.telegram.app.shutdown()
            except Exception:
                pass

        for bot in list(self.supervisor.bots.values()):
            await bot.stop()

        await self.supervisor.stop()
        await self.bus.stop()
        logger.info("[OrchestratorEngine] Shutdown complete.")

    def health(self) -> Dict[str, Any]:
        """Aggregate health status across the entire fleet."""
        return {
            "mode": self.mode,
            "running": self._running,
            "supervisor": self.supervisor.health_report(),
            "positions": self.execution_bot.active_positions if self.execution_bot else {},
            "metrics": self.journal_bot.get_performance_metrics(window_days=1) if self.journal_bot else {}
        }
