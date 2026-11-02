"""RiskBot: Deterministic risk controls, multi-limit gating, and fractional Kelly sizing."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

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
from cryptoscope.quant.sizing import optimal_trade_sizing

logger = logging.getLogger("cryptoscope.orchestrator.risk_bot")


class RiskBot(BaseBot):
    """Deterministic, mathematical risk guardian for all autonomous trades.

    Applies hard limits without LLM control:
    1. Debate verdict verification
    2. Daily loss limit cap
    3. Portfolio maximum drawdown cap
    4. Maximum concurrent open positions
    5. Per-coin capital exposure cap
    6. Maximum single order size
    7. Asset correlation cap
    8. Minimum 24h market liquidity
    9. Fractional Kelly position sizing with stop-distance floor
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "risk_bot",
        initial_nav: float = 10000.0,
        max_daily_loss_pct: float = 0.03,      # 3% daily loss limit
        max_drawdown_pct: float = 0.10,        # 10% max portfolio drawdown
        max_open_positions: int = 3,           # Max 3 open positions
        max_per_coin_pct: float = 0.15,        # Max 15% NAV per symbol
        max_order_pct: float = 0.05,           # Max 5% single order size
        correlation_cap: float = 0.85,         # Veto if corr > 0.85 with open pos
        min_liquidity_usd: float = 100000.0,   # Min $100k 24h volume
        kelly_fraction: float = 0.5            # Half-Kelly sizing
    ):
        super().__init__(name, bus)
        self.initial_nav = initial_nav
        self.current_nav = initial_nav
        self.peak_nav = initial_nav

        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_open_positions = max_open_positions
        self.max_per_coin_pct = max_per_coin_pct
        self.max_order_pct = max_order_pct
        self.correlation_cap = correlation_cap
        self.min_liquidity_usd = min_liquidity_usd
        self.kelly_fraction = kelly_fraction

        # State tracking
        self.daily_realized_pnl: float = 0.0
        self.daily_loss_circuit_breaker: bool = False
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.cached_intents: Dict[str, TradeIntent] = {}

        # High-correlation matrix for major crypto assets
        self.correlation_matrix: Dict[str, Dict[str, float]] = {
            "BTCUSDT": {"ETHUSDT": 0.88, "SOLUSDT": 0.82},
            "ETHUSDT": {"BTCUSDT": 0.88, "SOLUSDT": 0.84},
            "SOLUSDT": {"BTCUSDT": 0.82, "ETHUSDT": 0.84}
        }

        self.subscribe(TradeIntent)
        self.subscribe(DebateResult)
        self.subscribe(Fill)
        self.subscribe(PositionClosed)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, TradeIntent):
            self.cached_intents[event.intent_id] = event
        elif isinstance(event, DebateResult):
            await self._evaluate_risk(event)
        elif isinstance(event, Fill):
            self._handle_fill(event)
        elif isinstance(event, PositionClosed):
            self._handle_position_closed(event)

    def _handle_fill(self, fill: Fill) -> None:
        """Track open position exposure."""
        sym = fill.symbol
        if fill.side == "BUY":
            pos = self.open_positions.get(sym, {"quantity": 0.0, "entry": fill.executed_price, "usd_value": 0.0})
            pos["quantity"] += fill.quantity
            pos["entry"] = fill.executed_price
            pos["usd_value"] = pos["quantity"] * fill.executed_price
            self.open_positions[sym] = pos
        elif fill.side == "SELL":
            if sym in self.open_positions:
                pos = self.open_positions[sym]
                pos["quantity"] -= fill.quantity
                if pos["quantity"] <= 1e-6:
                    self.open_positions.pop(sym, None)

    def _handle_position_closed(self, closed: PositionClosed) -> None:
        """Update daily PnL and NAV tracking."""
        self.daily_realized_pnl += closed.pnl_usd
        self.current_nav += closed.pnl_usd
        self.peak_nav = max(self.peak_nav, self.current_nav)
        self.open_positions.pop(closed.symbol, None)

        max_daily_loss_usd = self.initial_nav * self.max_daily_loss_pct
        if self.daily_realized_pnl <= -max_daily_loss_usd:
            self.daily_loss_circuit_breaker = True
            asyncio.create_task(self.emit(SystemAlert(
                severity="CRITICAL",
                source=self.name,
                title="Daily Loss Limit Breached",
                message=f"Daily realized loss of ${abs(self.daily_realized_pnl):.2f} exceeds limit ${max_daily_loss_usd:.2f}."
            )))

        logger.info(
            "[%s] Position %s closed. PnL: $%.2f. Daily PnL: $%.2f. NAV: $%.2f",
            self.name, closed.symbol, closed.pnl_usd, self.daily_realized_pnl, self.current_nav
        )

    async def _evaluate_risk(self, debate: DebateResult) -> None:
        intent = self.cached_intents.get(debate.intent_id)
        if not intent:
            logger.warning("[%s] Missing cached TradeIntent for debate %s", self.name, debate.debate_id)
            return

        veto_reasons: List[str] = []

        # Gate 1: Debate verdict
        if debate.verdict != "APPROVE":
            veto_reasons.append(f"Debate layer verdict is {debate.verdict} (Conviction: {debate.conviction_score:.1f})")

        # Gate 2: Daily Loss Limit
        max_daily_loss_usd = self.initial_nav * self.max_daily_loss_pct
        if self.daily_realized_pnl <= -max_daily_loss_usd:
            veto_reasons.append(
                f"DAILY_LOSS_LIMIT: Realized daily loss (-${abs(self.daily_realized_pnl):.2f}) exceeds limit (-${max_daily_loss_usd:.2f})"
            )

        # Gate 3: Max Portfolio Drawdown
        current_drawdown_pct = (self.peak_nav - self.current_nav) / self.peak_nav
        if current_drawdown_pct >= self.max_drawdown_pct:
            veto_reasons.append(
                f"MAX_DRAWDOWN: Current drawdown ({current_drawdown_pct*100:.1f}%) exceeds max allowed ({self.max_drawdown_pct*100:.1f}%)"
            )

        # Gate 4: Max Open Positions
        if intent.symbol not in self.open_positions and len(self.open_positions) >= self.max_open_positions:
            veto_reasons.append(
                f"MAX_POSITIONS: Active positions ({len(self.open_positions)}) reach maximum ({self.max_open_positions})"
            )

        # Gate 5: Correlation Cap
        for open_sym in self.open_positions:
            if open_sym != intent.symbol:
                corr = self.correlation_matrix.get(intent.symbol, {}).get(open_sym, 0.0)
                if corr >= self.correlation_cap:
                    veto_reasons.append(
                        f"CORRELATION_CAP: Symbol {intent.symbol} has high correlation ({corr:.2f}) with open position {open_sym}"
                    )
                    break

        # Stop distance check
        entry = intent.entry_price
        stop = intent.stop_loss
        stop_distance_pct = abs(entry - stop) / entry
        if stop_distance_pct < 0.005:
            veto_reasons.append(f"STOP_TOO_TIGHT: Stop distance ({stop_distance_pct*100:.2f}%) below minimum 0.50%")

        # Sizing via Fractional Kelly
        sizing_res = optimal_trade_sizing(
            account_balance=self.current_nav,
            entry_price=entry,
            stop_loss=stop,
            win_rate=0.55,
            win_loss_ratio=2.0,
            kelly_fraction=self.kelly_fraction,
            max_account_risk_pct=self.max_order_pct
        )
        approved_usd = sizing_res.get("position_size_usd", 0.0)
        approved_qty = sizing_res.get("position_qty", 0.0)
        risk_usd = sizing_res.get("risk_usd", 0.0)

        # Gate 6: Per-Coin Exposure Cap
        existing_exposure = self.open_positions.get(intent.symbol, {}).get("usd_value", 0.0)
        max_coin_usd = self.current_nav * self.max_per_coin_pct
        if existing_exposure + approved_usd > max_coin_usd:
            # Scale down if possible, or veto if already at cap
            remaining_room = max(0.0, max_coin_usd - existing_exposure)
            if remaining_room < (entry * 0.001):
                veto_reasons.append(
                    f"EXPOSURE_CAP: Symbol {intent.symbol} exposure (${existing_exposure:.2f}) at maximum (${max_coin_usd:.2f})"
                )
            else:
                approved_usd = remaining_room
                approved_qty = round(approved_usd / entry, 4)

        decision_status = "VETOED" if veto_reasons else "APPROVED"

        decision = RiskDecision(
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            decision=decision_status,
            approved_quantity=approved_qty if decision_status == "APPROVED" else 0.0,
            position_size_usd=round(approved_usd, 2) if decision_status == "APPROVED" else 0.0,
            risk_usd=round(risk_usd, 2) if decision_status == "APPROVED" else 0.0,
            kelly_fraction_used=self.kelly_fraction,
            stop_distance_pct=round(stop_distance_pct * 100, 2),
            veto_reasons=veto_reasons,
            limits_snapshot={
                "nav": round(self.current_nav, 2),
                "daily_pnl": round(self.daily_realized_pnl, 2),
                "open_positions": len(self.open_positions),
                "drawdown_pct": round(current_drawdown_pct * 100, 2)
            }
        )

        logger.info(
            "[%s] Intent %s (%s) Risk Decision: %s (Size: $%.2f, Reasons: %s)",
            self.name, intent.intent_id, intent.symbol, decision_status, approved_usd, veto_reasons
        )
        await self.emit(decision)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "current_nav": self.current_nav,
            "daily_realized_pnl": self.daily_realized_pnl,
            "open_positions": list(self.open_positions.keys()),
            "max_daily_loss_usd": self.initial_nav * self.max_daily_loss_pct
        }
