"""RiskBot: Deterministic risk controls, multi-limit gating, and fractional Kelly sizing."""

import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    BaseEvent,
    DebateResult,
    Fill,
    PositionClosed,
    RiskDecision,
    RiskPreApproved,
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
        kelly_fraction: float = 0.5,           # Half-Kelly sizing
        fixed_risk_fraction: float = 0.005,    # 0.5% default fixed fractional risk
        enable_kelly_sizing: bool = False,     # Gated: requires >= 300 closed trades
        state_path: Optional[str] = None,      # persist breakers/NAV across restarts when set
        protections: Any = None,               # cryptoscope.execution.protections.ProtectionManager
        max_entries_per_day: Optional[int] = None,  # new positions per UTC day; env ZILLERS_MAX_TRADES_PER_DAY
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
        self.fixed_risk_fraction = fixed_risk_fraction
        self.enable_kelly_sizing = enable_kelly_sizing
        # Fewer, better trades: every round trip costs ~0.2% in fees, so cap new entries per day.
        if max_entries_per_day is None:
            try:
                max_entries_per_day = int(os.environ.get("ZILLERS_MAX_TRADES_PER_DAY", "12"))
            except ValueError:
                max_entries_per_day = 12
        self.max_entries_per_day = max(0, max_entries_per_day)

        # State tracking
        self.daily_entries: int = 0
        self.daily_realized_pnl: float = 0.0
        self.daily_loss_circuit_breaker: bool = False
        self.drawdown_circuit_breaker: bool = False
        self.closed_trades_count: int = 0
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.cached_intents: Dict[str, TradeIntent] = {}

        # High-correlation matrix for major crypto assets
        self.correlation_matrix: Dict[str, Dict[str, float]] = {
            "BTCUSDT": {"ETHUSDT": 0.88, "SOLUSDT": 0.82},
            "ETHUSDT": {"BTCUSDT": 0.88, "SOLUSDT": 0.84},
            "SOLUSDT": {"BTCUSDT": 0.82, "ETHUSDT": 0.84}
        }

        self._state_path: Optional[Path] = Path(state_path) if state_path else None
        self.protections = protections
        self._day = self._utc_day()
        self._load_state()

        self.subscribe(TradeIntent)
        self.subscribe(DebateResult)
        self.subscribe(Fill)
        self.subscribe(PositionClosed)

    # -- durable breaker state ------------------------------------------------
    @staticmethod
    def _utc_day() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _load_state(self) -> None:
        """Restore NAV/peak/breakers. Daily figures survive only within the same UTC day."""
        if self._state_path is None or not self._state_path.is_file():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self.current_nav = float(data["current_nav"])
            self.peak_nav = float(data["peak_nav"])
            self.drawdown_circuit_breaker = bool(data.get("drawdown_circuit_breaker", False))
            self.closed_trades_count = int(data.get("closed_trades_count", 0))
            if data.get("day") == self._day:
                self.daily_realized_pnl = float(data.get("daily_realized_pnl", 0.0))
                self.daily_entries = int(data.get("daily_entries", 0))
                self.daily_loss_circuit_breaker = bool(data.get("daily_loss_circuit_breaker", False))
        except (OSError, ValueError, KeyError, TypeError):
            # Unreadable risk state must fail closed rather than silently reset the breakers.
            logger.error("[%s] Risk state unreadable; latching drawdown breaker", self.name)
            self.drawdown_circuit_breaker = True

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        data = {
            "day": self._day,
            "daily_realized_pnl": self.daily_realized_pnl,
            "daily_entries": self.daily_entries,
            "daily_loss_circuit_breaker": self.daily_loss_circuit_breaker,
            "drawdown_circuit_breaker": self.drawdown_circuit_breaker,
            "current_nav": self.current_nav,
            "peak_nav": self.peak_nav,
            "closed_trades_count": self.closed_trades_count,
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, self._state_path)
        except OSError:
            logger.exception("[%s] Failed to persist risk state", self.name)

    def _roll_day(self) -> None:
        """Reset the daily-loss figures at the UTC day boundary (drawdown latch is never reset)."""
        today = self._utc_day()
        if today != self._day:
            self._day = today
            self.daily_realized_pnl = 0.0
            self.daily_entries = 0
            self.daily_loss_circuit_breaker = False
            self._save_state()

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, TradeIntent):
            self.cached_intents[event.intent_id] = event
        elif isinstance(event, DebateResult):
            await self._evaluate_risk(event)
        elif isinstance(event, Fill):
            self._handle_fill(event)
        elif isinstance(event, PositionClosed):
            self._handle_position_closed(event)

    def check_pre_trade_risk(self, intent: TradeIntent) -> Tuple[bool, List[str]]:
        """Deterministic pre-trade risk gating before expensive LLM deliberation."""
        veto_reasons = []
        self._roll_day()
        if not self._valid_prices(intent):
            return False, ['INVALID_PRICES: Finite positive prices and a protective stop are required.']

        if self.daily_loss_circuit_breaker:
            veto_reasons.append("DAILY_LOSS_LIMIT: Circuit breaker active.")

        cap = self._entry_cap_reason(intent)
        if cap:
            veto_reasons.append(cap)

        if self.protections is not None:
            locked, reasons = self.protections.is_locked(intent.symbol)
            if locked:
                veto_reasons.extend(reasons)

        current_drawdown_pct = (self.peak_nav - self.current_nav) / self.peak_nav if self.peak_nav > 0 else 0.0
        if current_drawdown_pct >= self.max_drawdown_pct:
            self.drawdown_circuit_breaker = True
        if self.drawdown_circuit_breaker:
            veto_reasons.append(f"MAX_DRAWDOWN: Drawdown ({current_drawdown_pct*100:.1f}%) exceeds limit.")

        if len(self.open_positions) >= self.max_open_positions and intent.symbol not in self.open_positions:
            veto_reasons.append(f"MAX_OPEN_POSITIONS: Already holding {len(self.open_positions)} positions.")

        for open_sym in self.open_positions:
            corr = self.correlation_matrix.get(intent.symbol, {}).get(open_sym, 0.0)
            if corr >= self.correlation_cap:
                veto_reasons.append(f"CORRELATION_CAP: Correlation {corr:.2f} with {open_sym} exceeds {self.correlation_cap}.")
                break

        stop_dist = abs(intent.entry_price - intent.stop_loss) / (intent.entry_price or 1.0)
        if stop_dist < 0.005:
            veto_reasons.append(f"STOP_TOO_TIGHT: Stop distance ({stop_dist*100:.2f}%) below minimum 0.50%.")

        return len(veto_reasons) == 0, veto_reasons

    def _entry_cap_reason(self, intent) -> Optional[str]:
        """Veto a NEW position once today's entry cap is used (adding to an open one is not an entry)."""
        self._roll_day()
        if intent.direction == "BUY" and intent.symbol not in self.open_positions \
                and self.daily_entries >= self.max_entries_per_day:
            return (f"MAX_DAILY_TRADES: {self.daily_entries} new positions today "
                    f"(cap {self.max_entries_per_day}, ZILLERS_MAX_TRADES_PER_DAY).")
        return None

    @staticmethod
    def _valid_prices(intent):
        values = (intent.entry_price,intent.stop_loss,intent.take_profit)
        if not all(type(v) in (int,float) and math.isfinite(v) and v > 0 for v in values):
            return False
        return ((intent.direction == 'BUY' and intent.stop_loss < intent.entry_price < intent.take_profit)
                or (intent.direction == 'SELL' and intent.take_profit < intent.entry_price < intent.stop_loss))

    def observe_portfolio_nav(self, nav):
        """Mark total portfolio equity and latch a drawdown breach on observation."""
        if not math.isfinite(nav):
            self.drawdown_circuit_breaker = True
            return
        self.current_nav = nav
        self.peak_nav = max(self.peak_nav,nav)
        if self.peak_nav <= 0 or (self.peak_nav-nav)/self.peak_nav >= self.max_drawdown_pct:
            self.drawdown_circuit_breaker = True
        self._save_state()

    def _handle_fill(self, fill: Fill) -> None:
        """Track open position exposure."""
        sym = fill.symbol
        if fill.side == "BUY":
            if sym not in self.open_positions:
                self._roll_day()
                self.daily_entries += 1
                self._save_state()
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
                else:
                    pos['usd_value'] = pos['quantity'] * pos['entry']

    def _handle_position_closed(self, closed: PositionClosed) -> None:
        """Update daily PnL and NAV tracking."""
        self._roll_day()
        if self.protections is not None:
            new_locks = self.protections.record_close(closed.symbol, closed.pnl_pct / 100.0, closed.pnl_usd, closed.exit_reason)
            for lk in new_locks:
                if lk.guard == "CooldownPeriod":
                    continue  # routine; not worth a Telegram message
                note = SystemAlert(severity="WARNING", source=self.name, title=f"Protection: {lk.guard}",
                                   message=f"{'ALL pairs' if lk.pair == '*' else lk.pair} locked: {lk.reason}")
                try:
                    asyncio.get_running_loop().create_task(self.emit(note))
                except RuntimeError:
                    logger.warning("[%s] %s", self.name, note.message)
        self.daily_realized_pnl += closed.pnl_usd
        self.current_nav += closed.pnl_usd
        self.peak_nav = max(self.peak_nav, self.current_nav)
        self.closed_trades_count += 1
        self.open_positions.pop(closed.symbol, None)

        max_daily_loss_usd = self.initial_nav * self.max_daily_loss_pct
        if self.daily_realized_pnl <= -max_daily_loss_usd:
            self.daily_loss_circuit_breaker = True
            alert = SystemAlert(
                severity="CRITICAL",
                source=self.name,
                title="Daily Loss Limit Breached",
                message=f"Daily realized loss of ${abs(self.daily_realized_pnl):.2f} exceeds limit ${max_daily_loss_usd:.2f}."
            )
            try:
                asyncio.get_running_loop().create_task(self.emit(alert))
            except RuntimeError:
                logger.critical("[%s] %s (no event loop to publish alert)", self.name, alert.message)

        self._save_state()
        logger.info(
            "[%s] Position %s closed. PnL: $%.2f. Daily PnL: $%.2f. NAV: $%.2f",
            self.name, closed.symbol, closed.pnl_usd, self.daily_realized_pnl, self.current_nav
        )

    async def _evaluate_risk(self, debate: DebateResult) -> None:
        if self.halt_state.snapshot()['halted']:
            return
        intent = self.cached_intents.get(debate.intent_id)
        if not intent:
            logger.warning("[%s] Missing cached TradeIntent for debate %s", self.name, debate.debate_id)
            return

        if not self._valid_prices(intent):
            await self.emit(RiskDecision(intent_id=intent.intent_id,symbol=intent.symbol,
                decision='VETOED',veto_reasons=['INVALID_PRICES: Invalid trade bracket.']))
            return

        veto_reasons: List[str] = []

        # Gate 1: Debate verdict
        if debate.verdict != "APPROVE":
            veto_reasons.append(f"Debate layer verdict is {debate.verdict} (Conviction: {debate.conviction_score:.1f})")

        # Gate 1m: THX-02 / Laya meta-label filter. Veto-only, and only when the operator enforces it.
        from cryptoscope.agents.decision_models import veto_reason
        meta_veto = veto_reason(getattr(debate, "meta", None))
        if meta_veto:
            veto_reasons.append(meta_veto)

        # Gate 1a: daily entry cap (re-checked here: fills may have landed during the debate)
        cap = self._entry_cap_reason(intent)
        if cap:
            veto_reasons.append(cap)

        # Gate 1b: Protections (cooldown, stop-loss guard, low-profit pair, closed-trade drawdown)
        if self.protections is not None:
            locked, reasons = self.protections.is_locked(intent.symbol)
            if locked:
                veto_reasons.extend(reasons)

        # Gate 2: Daily Loss Limit
        max_daily_loss_usd = self.initial_nav * self.max_daily_loss_pct
        if self.daily_realized_pnl <= -max_daily_loss_usd:
            veto_reasons.append(
                f"DAILY_LOSS_LIMIT: Realized daily loss (-${abs(self.daily_realized_pnl):.2f}) exceeds limit (-${max_daily_loss_usd:.2f})"
            )

        # Gate 3: Max Portfolio Drawdown
        current_drawdown_pct = (self.peak_nav - self.current_nav) / self.peak_nav
        if current_drawdown_pct >= self.max_drawdown_pct:
            self.drawdown_circuit_breaker = True
        if self.drawdown_circuit_breaker:
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

        # Sizing via Default Fixed Fractional Risk (Kelly gated behind flag & 300+ closed trades)
        sizing_res = optimal_trade_sizing(
            account_balance=self.current_nav,
            entry_price=entry,
            stop_loss=stop,
            win_rate=0.55,
            win_loss_ratio=2.0,
            kelly_fraction=self.kelly_fraction,
            max_account_risk_pct=self.max_order_pct * 100.0,
            sizing_mode="KELLY" if self.enable_kelly_sizing else "FIXED_FRACTIONAL",
            fixed_risk_fraction=self.fixed_risk_fraction,
            enable_kelly_sizing=self.enable_kelly_sizing,
            closed_trades_count=self.closed_trades_count,
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
                approved_qty = min(approved_qty,approved_usd / entry)

        # Enforce advertised notional limits in fixed-fractional mode too.
        # Round down so precision handling never increases approved exposure.
        approved_usd = min(approved_usd,self.current_nav * self.max_order_pct,
                           max(0.0,max_coin_usd-existing_exposure))
        # Risk-only scaling AFTER every cap: toxic order flow (bar VPIN) or a high-volatility regime shrink
        # the final trade. Clamped to [0, 1], so it can never enlarge a position.
        from cryptoscope.quant.flow_risk import size_multiplier
        scale = size_multiplier((intent.metadata or {}).get("features"))
        mult = min(1.0, max(0.0, float(scale["multiplier"])))
        if mult < 1.0:
            approved_usd *= mult
            logger.info("[%s] %s size x%.2f (%s)", self.name, intent.symbol, mult, "; ".join(scale["reasons"]))
        approved_qty = math.floor(min(approved_qty,approved_usd/entry)*100_000_000)/100_000_000
        approved_usd = approved_qty * entry
        risk_usd = approved_qty * abs(entry-stop)
        if not math.isfinite(approved_qty) or approved_qty <= 0:
            veto_reasons.append('INVALID_SIZE: No positive size within limits.')

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
            "max_daily_loss_usd": self.initial_nav * self.max_daily_loss_pct,
            "daily_entries": self.daily_entries,
            "max_entries_per_day": self.max_entries_per_day,
            "drawdown_halted": self.drawdown_circuit_breaker
        }
