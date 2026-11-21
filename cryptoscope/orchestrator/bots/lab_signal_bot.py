"""LabSignalBot: turns Strategy Lab strategies that PASSED the promotion gate into live fleet signals.

The Lab (desk/strategy_lab.py) backtests every candidate strategy and promotes one only if it clears
>= 100 out-of-sample trades, Deflated Sharpe p < 0.05, PBO < 0.3 and positive expectancy after fees.
Promotions are recorded per (symbol, interval) in work/runtime/promoted_strategies.json.

This bot reads that file (re-reading when it changes) and, for each fleet symbol, runs only the
strategies promoted for that exact symbol AND the fleet's candle interval: a strategy validated on BTC
daily bars says nothing about ADA on 15m bars. When a promoted strategy's position flips from flat to
long on the latest closed bar, it emits a BUY Signal. Everything downstream still applies: StrategyBot
bracket, debate, THX-02/Laya meta-label, RiskBot gates and sizing, ExecutionBot. Spot only, long only.

With nothing promoted (today's state), the bot stays idle and says so in its health report.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal

logger = logging.getLogger(__name__)


class LabSignalBot(BaseBot):
    def __init__(self, bus: EventBus, name: str = "lab_signal_bot", interval: str = "15m",
                 promoted_path: Optional[Path] = None, min_bars: int = 60):
        super().__init__(name, bus)
        from cryptoscope.desk.strategy_lab import PROMOTED_PATH
        self.interval = interval
        self.promoted_path = Path(promoted_path or PROMOTED_PATH)
        self.min_bars = min_bars
        self._mtime: Optional[float] = None
        self._promoted: List[Dict[str, Any]] = []
        self._last_bar: Dict[tuple, Any] = {}     # (symbol, strategy) -> open_time of the last bar evaluated
        self.signals_emitted = 0
        self.errors = 0
        self.subscribe(MarketUpdate)

    def _reload(self) -> None:
        try:
            mtime = self.promoted_path.stat().st_mtime
        except OSError:
            self._promoted, self._mtime = [], None
            return
        if mtime == self._mtime:
            return
        from cryptoscope.desk.strategy_lab import load_promoted_strategies
        self._promoted, self._mtime = load_promoted_strategies(self.promoted_path), mtime
        logger.info("[%s] %d promoted strategies loaded", self.name, len(self._promoted))

    def active_for(self, symbol: str) -> List[Dict[str, Any]]:
        self._reload()
        return [p for p in self._promoted if p.get("symbol") == symbol and p.get("interval") == self.interval]

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            await self._evaluate(event)

    async def _evaluate(self, update: MarketUpdate) -> None:
        active = self.active_for(update.symbol)
        candles = update.candles or []
        if not active or len(candles) < self.min_bars:
            return
        from cryptoscope.desk.strategy_lab import STRATEGIES
        bar_id = candles[-1].get("open_time", len(candles))
        for promo in active:
            key = promo["strategy"]
            if self._last_bar.get((update.symbol, key)) == bar_id:
                continue                                  # this closed bar was already evaluated
            self._last_bar[(update.symbol, key)] = bar_id
            try:
                pos = list(STRATEGIES[key][2](candles))
            except Exception as exc:
                self.errors += 1
                logger.warning("[%s] %s on %s failed: %s", self.name, key, update.symbol, exc)
                continue
            if len(pos) < 2 or not (pos[-1] > 0 and pos[-2] <= 0):
                continue                                  # only a fresh flat -> long entry is a signal
            self.signals_emitted += 1
            await self.emit(Signal(
                strategy_id=f"lab:{key}", symbol=update.symbol, timeframe=self.interval, direction="BUY",
                confidence=0.7,
                indicators={"price": update.price, "lab_strategy": key, "lab_oos_trades": promo.get("oos_trades"),
                            "lab_dsr_p": promo.get("dsr_p"), "lab_pbo": promo.get("pbo")},
                reasons=[f"Promoted Lab strategy {promo.get('label', key)} entered long "
                         f"(OOS {promo.get('oos_trades')} trades, DSR p {promo.get('dsr_p')}, PBO {promo.get('pbo')})"],
            ))

    def get_health_details(self) -> Dict[str, Any]:
        self._reload()
        mine = [p for p in self._promoted if p.get("interval") == self.interval]
        return {"interval": self.interval, "promoted_total": len(self._promoted),
                "promoted_for_interval": [f"{p['symbol']}:{p['strategy']}" for p in mine],
                "signals_emitted": self.signals_emitted, "errors": self.errors,
                "state": "active" if mine else "idle (no strategy has passed the Lab gate for this interval)"}
