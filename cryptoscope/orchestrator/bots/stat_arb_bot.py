"""StatArbStrategyBot: Cointegrated pairs trading and statistical arbitrage strategy bot."""

import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal
from cryptoscope.autotrader.strategies.stat_arb_pairs import StatArbPairsStrategy

logger = logging.getLogger("cryptoscope.orchestrator.stat_arb_bot")


class StatArbStrategyBot(BaseBot):
    """Executes statistical arbitrage on cointegrated asset pairs (e.g. ETHUSDT vs BTCUSDT)."""

    def __init__(
        self,
        bus: EventBus,
        name: str = "stat_arb_bot",
        pair: tuple = ("ETHUSDT", "BTCUSDT"),
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.25,
        stop_zscore: float = 3.5,
        window: int = 30,
        cooldown_sec: float = 15.0,
    ):
        super().__init__(name, bus)
        self.pair = pair
        self.strategy = StatArbPairsStrategy(
            entry_zscore=entry_zscore,
            exit_zscore=exit_zscore,
            stop_zscore=stop_zscore,
            window=window,
        )
        self.cooldown_sec = cooldown_sec
        self.candle_cache: Dict[str, List[Dict[str, Any]]] = {
            self.pair[0]: [],
            self.pair[1]: [],
        }
        self.last_signal_time: float = 0.0
        self.signals_generated_count: int = 0
        self.is_paused: bool = False

        self.subscribe(MarketUpdate)

    def pause(self, reason: str = "") -> None:
        self.is_paused = True
        logger.warning("[%s] Paused: %s", self.name, reason)

    def resume(self) -> None:
        self.is_paused = False
        logger.info("[%s] Resumed operations", self.name)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            await self._on_market_update(event)

    async def _on_market_update(self, update: MarketUpdate) -> None:
        if self.is_paused:
            return

        if update.symbol in self.candle_cache and update.candles:
            self.candle_cache[update.symbol] = update.candles

        sym_a, sym_b = self.pair
        candles_a = self.candle_cache.get(sym_a, [])
        candles_b = self.candle_cache.get(sym_b, [])

        if len(candles_a) < 35 or len(candles_b) < 35:
            return

        now = time.time()
        if (now - self.last_signal_time) < self.cooldown_sec:
            return

        try:
            res = self.strategy.evaluate_pair(candles_a, candles_b, symbol_a=sym_a, symbol_b=sym_b)
            if not res:
                return

            side = res.get("side")
            # In long spread: Buy A, Short B
            # We emit signal for primary leg A
            direction = "HOLD"
            primary_sym = sym_a
            if side == "LONG_SPREAD":
                direction = "BUY"
            elif side == "SHORT_SPREAD":
                direction = "SELL"

            if direction == "HOLD":
                return

            self.last_signal_time = now
            self.signals_generated_count += 1

            sig = Signal(
                strategy_id="stat_arb_pairs",
                symbol=primary_sym,
                timeframe="15m",
                direction=direction,
                confidence=float(res.get("confidence", 0.70)),
                indicators={
                    "price": res.get("entry_price_a"),
                    "zscore": res.get("zscore"),
                    "hedge_ratio_beta": res.get("hedge_ratio_beta"),
                    "half_life_bars": res.get("half_life_bars"),
                    "is_cointegrated": res.get("is_cointegrated"),
                    "spread_side": side,
                    "secondary_symbol": sym_b,
                },
                reasons=[res.get("reason", "Stat-arb cointegrated spread mean-reversion signal")],
            )
            logger.info(
                "[%s] Signal emitted for %s (%s spread): %s (Z=%.2f)",
                self.name, primary_sym, side, direction, res.get("zscore", 0.0)
            )
            await self.emit(sig)

        except Exception as exc:
            logger.error("[%s] Pair evaluation error: %s", self.name, exc)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "pair": self.pair,
            "candles_cached": {k: len(v) for k, v in self.candle_cache.items()},
            "signals_generated_count": self.signals_generated_count,
            "is_paused": self.is_paused,
        }
