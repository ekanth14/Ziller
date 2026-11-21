"""StrategyBot: Evaluates composite signals and submits TradeIntent proposals."""

import logging
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import BaseEvent, MarketUpdate, Signal, TradeIntent

logger = logging.getLogger("cryptoscope.orchestrator.strategy_bot")


STOP_FLOOR = 0.0052


def bracket(profile: str, atr_pct: float):
    """Stop and take-profit distances (fractions of entry) and holding horizon in 15m bars.

    SCALP: target = clamp(1.5 x ATR%, 0.5%, 1.0%); stop = clamp(1.2 x ATR%, 0.5%, target).
           Binance spot costs ~0.2% round trip, so a 0.5% target nets ~0.3% and a 0.5% stop
           loses ~0.7%: the strategy needs to win more often than it loses to profit.
    SWING: stop = max(1.5 x ATR%, 0.5%), target = 2 x stop (the original 2:1 bracket).
    STOP_FLOOR (0.52%) sits just above RiskBot's 0.50% minimum so rounding never trips it.
    """
    atr_pct = max(0.0, float(atr_pct or 0.0))
    if profile == "SWING":
        stop = max(1.5 * atr_pct, STOP_FLOOR)
        return stop, 2 * stop, 48
    target = min(max(1.5 * atr_pct, 0.005), 0.010)
    stop = min(max(1.2 * atr_pct, STOP_FLOOR), max(target, STOP_FLOOR))
    return stop, target, 16


class StrategyBot(BaseBot):
    """Orchestrates algorithmic strategy execution and proposes TradeIntent.

    Consumes Signal and MarketUpdate events. Formulates entry, protective stop-loss,
    and take-profit targets, submitting proposals to the Debate layer.
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "strategy_bot",
        min_confidence: float = 0.65,
        cooldown_sec: float = 5.0,
        spot_only: bool = True,
        repeat_window_sec: float = 900.0,
        profile: Optional[str] = None,
    ):
        super().__init__(name, bus)
        self.min_confidence = min_confidence
        self.cooldown_sec = cooldown_sec
        self.spot_only = spot_only
        self.repeat_window_sec = repeat_window_sec
        import os
        # SCALP (default): take profit 0.5-1.0% sized to volatility; SWING: the original 2R bracket.
        self.profile = (profile or os.environ.get("ZILLERS_TRADE_PROFILE", "SCALP")).upper()
        self._last_proposal: Dict[str, tuple] = {}
        self.suppressed_shorts = 0
        self.suppressed_repeats = 0
        self.is_paused: bool = False
        self.pause_reason: str = ""
        self.latest_prices: Dict[str, float] = {}
        self.latest_candles: Dict[str, list] = {}   # for bar-VPIN and volatility regime (risk-only inputs)
        self.last_signal_time: Dict[str, float] = {}
        self.proposed_intents_count: int = 0

        self.subscribe(MarketUpdate)
        self.subscribe(Signal)

    @property
    def paused(self) -> bool:
        return self.is_paused or self.halt_state.snapshot()['halted']

    def pause(self, reason: str = "Operator paused") -> None:
        # Emergency state has one authority. Do not leave a second emergency
        # latch in memory that the local administrator cannot clear.
        if not self.halt_state.snapshot()['halted']:
            self.is_paused = True
        self.pause_reason = reason
        logger.warning("[%s] Paused: %s", self.name, reason)

    def resume(self) -> None:
        self.is_paused = False
        self.pause_reason = ""
        logger.info("[%s] Resumed operations.", self.name)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, MarketUpdate):
            self.latest_prices[event.symbol] = event.price
            if event.candles:
                self.latest_candles[event.symbol] = event.candles
        elif isinstance(event, Signal):
            await self._evaluate_signal(event)

    async def _evaluate_signal(self, sig: Signal) -> None:
        if self.is_paused or self.halt_state.snapshot()['halted']:
            logger.debug("[%s] Signal discarded: strategy bot paused (%s)", self.name, self.pause_reason)
            return

        if sig.direction not in {"BUY", "SELL"}:
            return

        if sig.confidence < self.min_confidence:
            return

        # Spot account: a SELL signal is not an entry (no borrowing). Exits are handled by
        # the execution layer's stops/targets, so short proposals are dropped here.
        if self.spot_only and sig.direction == "SELL":
            self.suppressed_shorts += 1
            return

        now = time.time()
        last_time = self.last_signal_time.get(sig.symbol, 0.0)
        if (now - last_time) < self.cooldown_sec:
            logger.debug("[%s] Suppressing duplicate signal for %s within cooldown", self.name, sig.symbol)
            return
        self.last_signal_time[sig.symbol] = now

        price = sig.indicators.get("price") or self.latest_prices.get(sig.symbol)
        if not price or price <= 0:
            return

        atr = sig.indicators.get("atr") or self._atr(sig.symbol) or price * 0.015
        entry = price
        stop_pct, target_pct, horizon = bracket(self.profile, atr / price if price else 0.015)
        sign = 1 if sig.direction == "BUY" else -1
        # 8 significant digits: cheap coins (e.g. 0.0213) lose their bracket with fixed 4-decimal rounding.
        stop = float(f"{entry * (1 - sign * stop_pct):.8g}")
        target = float(f"{entry * (1 + sign * target_pct):.8g}")

        # The same symbol/direction/price was already proposed recently (unchanged candle): skip.
        key = (sig.direction, round(entry, 8))
        last = self._last_proposal.get(sig.symbol)
        if last and last[0] == key and now - last[1] < self.repeat_window_sec:
            self.suppressed_repeats += 1
            return
        self._last_proposal[sig.symbol] = (key, now)

        intent = TradeIntent(
            strategy_id=sig.strategy_id,
            symbol=sig.symbol,
            direction=sig.direction,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            horizon_bars=horizon,
            reasons=sig.reasons + [f"Signal confidence {sig.confidence:.2f}",
                                   f"{self.profile}: target {target_pct:.2%}, stop {stop_pct:.2%}"],
            # Facts known at this bar, for the THX-02 / Laya meta-label check (numbers and short labels only).
            metadata={"features": {**{k: v for k, v in (sig.indicators or {}).items()
                                      if isinstance(v, (int, float, str)) and not isinstance(v, bool)
                                      and (not isinstance(v, str) or len(v) <= 40)},
                                   "confidence": sig.confidence, "strategy": sig.strategy_id,
                                   "atr_pct": atr / price if price else None,
                                   **self._flow_features(sig.symbol)}},
        )
        self.proposed_intents_count += 1
        logger.info("[%s] Proposing %s %s @ %.4f (SL: %.4f, TP: %.4f)", self.name, intent.direction, intent.symbol, entry, stop, target)
        await self.emit(intent)

    def _atr(self, symbol: str, n: int = 14) -> Optional[float]:
        """Wilder-style simple ATR(n) from the latest closed candles, or None."""
        c = self.latest_candles.get(symbol) or []
        if len(c) <= n:
            return None
        try:
            trs = [max(float(b["high"]) - float(b["low"]), abs(float(b["high"]) - float(a["close"])),
                       abs(float(b["low"]) - float(a["close"]))) for a, b in zip(c[-n - 1:-1], c[-n:])]
        except (KeyError, TypeError, ValueError):
            return None
        return sum(trs) / n if trs else None

    def _flow_features(self, symbol: str) -> Dict[str, Any]:
        """Context for the THX-02 / Laya meta-label and RiskBot's risk-only sizing, from closed candles.

        VPIN + volatility regime (may shrink size), and RSI(14), 4h / 24h returns, EMA20/50 trend and the
        scanner tier (descriptive only). Every value uses bars up to the latest close: no lookahead.
        """
        from cryptoscope.quant.flow_risk import vol_regime, vpin_state
        candles = self.latest_candles.get(symbol) or []
        out: Dict[str, Any] = {}
        try:
            v, r = vpin_state(candles), vol_regime(candles)
            out.update({"vpin": v["vpin"], "vpin_pctile": v["vpin_pctile"], "vpin_toxic": v["toxic"],
                        "regime": r["regime"], "vol_ratio": r["vol_ratio"]})
        except Exception:
            pass
        try:
            closes = [float(c["close"]) for c in candles]
        except (KeyError, TypeError, ValueError):
            closes = []
        bars_per_hour = {"1m": 60, "5m": 12, "15m": 4, "30m": 2, "1h": 1}.get(getattr(self, "interval", "15m"), 4)
        if len(closes) > 15:
            gains = [max(0.0, b - a) for a, b in zip(closes[-15:-1], closes[-14:])]
            losses = [max(0.0, a - b) for a, b in zip(closes[-15:-1], closes[-14:])]
            avg_l = sum(losses) / 14
            out["rsi"] = round(100.0 if avg_l == 0 else 100 - 100 / (1 + (sum(gains) / 14) / avg_l), 1)
        for key, hours in (("r4h", 4), ("r24h", 24)):
            k = hours * bars_per_hour
            if len(closes) > k and closes[-k - 1] > 0:
                out[key] = round(closes[-1] / closes[-k - 1] - 1, 5)
        if len(closes) >= 50:
            def ema(xs, n):
                a, e = 2 / (n + 1), xs[0]
                for x in xs[1:]:
                    e = a * x + (1 - a) * e
                return e
            out["ema_trend"] = "up" if ema(closes, 20) > ema(closes, 50) else "down"
        tier = self._scanner_tier(symbol)
        if tier:
            out["tier"] = tier
        return out

    def _scanner_tier(self, symbol: str) -> Optional[str]:
        """Tier (TREND / SHORT_TERM / POTENTIAL) the autopilot picked this coin from, if logged."""
        from cryptoscope.desk.pnl import load_tier_log
        path = getattr(self, "tier_log_path", None)
        if path is None:
            from pathlib import Path
            path = Path(__file__).resolve().parents[3] / "work" / "runtime" / "scanner_tiers.jsonl"
        tier = None
        for rec in load_tier_log(path):
            tier = rec["tiers"].get(symbol, tier)
        return tier

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "proposed_intents_count": self.proposed_intents_count
        }
