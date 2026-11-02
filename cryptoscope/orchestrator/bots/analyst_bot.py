"""AnalystBot: Computes market structure, EMA trend crosses, and price action signals."""

import logging
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal

logger = logging.getLogger("cryptoscope.orchestrator.analyst_bot")


class AnalystBot(BaseBot):
    """Technical market structure and trend analyst.

    Consumes MarketUpdate events and emits directional Signal events.
    """

    def __init__(self, bus: EventBus, name: str = "analyst_bot"):
        super().__init__(name, bus)
        self.subscribe(MarketUpdate)
        self.last_signals: Dict[str, Signal] = {}

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            await self._analyze_market(event)

    async def _analyze_market(self, update: MarketUpdate) -> None:
        candles = update.candles
        if len(candles) < 20:
            return

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]

        # Fast and slow moving averages
        fast_ema = self._calc_ema(closes, 9)
        slow_ema = self._calc_ema(closes, 21)

        # Average True Range (ATR)
        atr = self._calc_atr(highs, lows, closes, 14)

        prev_fast = self._calc_ema(closes[:-1], 9)
        prev_slow = self._calc_ema(closes[:-1], 21)

        direction = "HOLD"
        confidence = 0.5
        reasons = []

        if fast_ema > slow_ema and prev_fast <= prev_slow:
            direction = "BUY"
            confidence = 0.75
            reasons.append("Bullish 9/21 EMA golden cross")
        elif fast_ema < slow_ema and prev_fast >= prev_slow:
            direction = "SELL"
            confidence = 0.75
            reasons.append("Bearish 9/21 EMA death cross")
        elif fast_ema > slow_ema and closes[-1] > fast_ema:
            direction = "BUY"
            confidence = 0.65
            reasons.append("Trend continuation above 9 EMA")
        elif fast_ema < slow_ema and closes[-1] < fast_ema:
            direction = "SELL"
            confidence = 0.65
            reasons.append("Trend continuation below 9 EMA")

        sig = Signal(
            strategy_id="trend_structure",
            symbol=update.symbol,
            timeframe="15m",
            direction=direction,
            confidence=confidence,
            indicators={
                "price": update.price,
                "fast_ema": round(fast_ema, 4),
                "slow_ema": round(slow_ema, 4),
                "atr": round(atr, 4),
            },
            reasons=reasons
        )
        self.last_signals[update.symbol] = sig
        await self.emit(sig)

    @staticmethod
    def _calc_ema(values: List[float], span: int) -> float:
        if not values:
            return 0.0
        multiplier = 2.0 / (span + 1)
        ema = values[0]
        for val in values[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    @staticmethod
    def _calc_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(closes) < 2:
            return 0.0
        tr_list = []
        for i in range(1, len(closes)):
            h = highs[i]
            l = lows[i]
            prev_c = closes[i - 1]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        if not tr_list:
            return 0.0
        recent = tr_list[-period:]
        return sum(recent) / len(recent)

    def get_health_details(self) -> Dict[str, Any]:
        return {"last_signals": {s: sig.direction for s, sig in self.last_signals.items()}}
