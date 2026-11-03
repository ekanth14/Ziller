"""DataBot: Ingests market feeds and dispatches normalized MarketUpdate events."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate
from cryptoscope.market_data.candle_store import CandleStore

logger = logging.getLogger("cryptoscope.orchestrator.data_bot")


class DataBot(BaseBot):
    """Responsible for feeding continuous, truthful market data into the event bus.

    Supports live polling from CandleStore / exchange feeds and manual candle replay for testing.
    """

    def __init__(
        self,
        bus: EventBus,
        symbols: Optional[List[str]] = None,
        poll_interval: float = 1.0,
        candle_store: Optional[CandleStore] = None,
        name: str = "data_bot"
    ):
        super().__init__(name, bus)
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] if symbols is None else list(symbols)
        self.poll_interval = poll_interval
        self.candle_store = candle_store or CandleStore()
        # symbol -> last emitted MarketUpdate
        self.latest_updates: Dict[str, MarketUpdate] = {}

    async def on_event(self, event: BaseEvent) -> None:
        """DataBot produces market updates; no inbound trade events to consume."""
        pass

    async def run(self) -> None:
        """Periodic polling loop fetching real candles from SQLite store."""
        while self._running:
            self._last_heartbeat = time.time()
            for sym in self.symbols:
                try:
                    candles = self.candle_store.load_candles(sym, "15m", limit=50)
                    if not candles:
                        candles = self.candle_store.load_candles(sym, "5m", limit=50)

                    if candles:
                        latest = candles[-1]
                        price = float(latest["close"])
                        high = float(latest["high"])
                        low = float(latest["low"])
                        vol = float(latest.get("volume", 0.0))
                        spread = 0.0002  # ~2 bps typical

                        mu = MarketUpdate(
                            symbol=sym,
                            price=price,
                            bid=round(price * (1.0 - spread / 2), 4),
                            ask=round(price * (1.0 + spread / 2), 4),
                            high_24h=high,
                            low_24h=low,
                            volume_24h=vol,
                            spread_pct=spread * 100,
                            candles=candles,
                            source="candle_store"
                        )
                        self.latest_updates[sym] = mu
                        await self.emit(mu)
                except Exception as exc:
                    logger.warning("[%s] Failed to fetch data for %s: %s", self.name, sym, exc)

            await asyncio.sleep(self.poll_interval)

    async def feed_candle(self, symbol: str, candle: Dict[str, Any], history: Optional[List[Dict[str, Any]]] = None) -> MarketUpdate:
        """Manual injection method for historical backtesting and unit test replays."""
        price = float(candle["close"])
        high = float(candle.get("high", price))
        low = float(candle.get("low", price))
        vol = float(candle.get("volume", 0.0))
        candles = (history or []) + [candle]

        mu = MarketUpdate(
            symbol=symbol,
            price=price,
            bid=round(price * 0.9999, 4),
            ask=round(price * 1.0001, 4),
            high_24h=high,
            low_24h=low,
            volume_24h=vol,
            spread_pct=0.02,
            candles=candles,
            source="replay"
        )
        self.latest_updates[symbol] = mu
        self.events_processed += 1
        await self.emit(mu)
        return mu

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "latest_prices": {s: u.price for s, u in self.latest_updates.items()}
        }
