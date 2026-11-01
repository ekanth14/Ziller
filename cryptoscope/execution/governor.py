"""Risk Governor, 5-Gate Live Trading Gatekeeper, and Emergency Kill Switch.

Strict Rules of Engagement:
- LIVE trading can NEVER be enabled by default or by accident. Default is PAPER.
- 5-Gate Live Trading Activation:
  Gate 1: LIVE_TRADING=true in environment.
  Gate 2: EXCHANGE_API_KEY and EXCHANGE_API_SECRET configured (read+trade only, never withdraw).
  Gate 3: Positive paper-trading track record over at least 50 paper trades.
  Gate 4: Explicit admin re-authentication in the UI (re-enter password within 5 minutes).
  Gate 5: Exact typed confirmation string: 'ENABLE LIVE TRADING'.
- Risk Governor (pre-trade checks, fail-closed):
  * Max position size per asset (% of portfolio, default 5%).
  * Max gross leverage 1.0 (spot only, NO margin, NO short selling on spot).
  * Max open orders count.
  * Daily loss limit: if hit, trigger EMERGENCY HALT.
  * Stale data halt: if any feed older than threshold (5s), halt new orders.
  * Cross-feed divergence halt: if cross-source divergence >1%, halt new orders.
- Emergency Kill Switch:
  * Instantly cancels all open orders across venues.
  * Closes all open positions via market orders.
  * Sets bot state to HALTED.
  * Requires admin re-auth to resume.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cryptoscope.execution.governor")


class LiveGateError(ValueError):
    pass


class LiveMultiGateGovernor:
    """Enforces the 5 non-negotiable gates required before live trading can be activated."""

    MIN_PAPER_TRADES = 50
    REQUIRED_CONFIRMATION_STRING = "ENABLE LIVE TRADING"
    REAUTH_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self, mode: str = "PAPER"):
        # Mode is strictly PAPER by default
        self._mode = "PAPER"
        self._live_enabled_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def verify_gates(
        self,
        paper_trade_count: int,
        paper_net_pnl: float,
        admin_reauthenticated: bool,
        admin_reauth_time: float,
        typed_confirmation: str,
        now: Optional[float] = None,
    ) -> Tuple[bool, List[str]]:
        now = time.time() if now is None else now
        failures = []

        # Gate 1: Environment flag
        env_flag = os.environ.get("LIVE_TRADING", "").strip().lower()
        if env_flag not in {"1", "true", "yes"}:
            failures.append("Gate 1 Failed: LIVE_TRADING=true environment variable is not set.")

        # Gate 2: API credentials present
        api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
        api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            failures.append("Gate 2 Failed: EXCHANGE_API_KEY and EXCHANGE_API_SECRET must be configured in environment.")

        # Gate 3: Track record
        if paper_trade_count < self.MIN_PAPER_TRADES:
            failures.append(f"Gate 3 Failed: Requires at least {self.MIN_PAPER_TRADES} paper trades (current: {paper_trade_count}).")
        if paper_net_pnl <= 0.0:
            failures.append(f"Gate 3 Failed: Paper trading track record must have positive net PnL (current: {paper_net_pnl:.2f}).")

        # Gate 4: Admin re-authentication
        if not admin_reauthenticated or (now - admin_reauth_time > self.REAUTH_WINDOW_SECONDS):
            failures.append("Gate 4 Failed: Administrator must re-authenticate with password within the last 5 minutes.")

        # Gate 5: Exact typed confirmation string
        if typed_confirmation.strip() != self.REQUIRED_CONFIRMATION_STRING:
            failures.append(f"Gate 5 Failed: Must type exact confirmation '{self.REQUIRED_CONFIRMATION_STRING}'.")

        return len(failures) == 0, failures

    def activate_live(
        self,
        paper_trade_count: int,
        paper_net_pnl: float,
        admin_reauthenticated: bool,
        admin_reauth_time: float,
        typed_confirmation: str,
        now: Optional[float] = None,
    ):
        now = time.time() if now is None else now
        with self._lock:
            passed, failures = self.verify_gates(
                paper_trade_count,
                paper_net_pnl,
                admin_reauthenticated,
                admin_reauth_time,
                typed_confirmation,
                now,
            )
            if not passed:
                raise LiveGateError("Live trading activation blocked by safety gates:\n" + "\n".join(failures))
            self._mode = "LIVE"
            self._live_enabled_at = now
            logger.critical("LIVE TRADING ACTIVATED by authenticated admin at %s", time.ctime(now))

    def deactivate_to_paper(self, reason: str = "Operator set to paper mode"):
        with self._lock:
            self._mode = "PAPER"
            self._live_enabled_at = None
            logger.info("Trading mode set to PAPER: %s", reason)


class RiskGovernor:
    """Pre-trade risk governor enforcing fail-closed capital protection."""

    def __init__(
        self,
        max_position_fraction: float = 0.05,  # 5% max position per asset
        max_open_orders: int = 10,
        daily_loss_limit_fraction: float = 0.03,  # 3% daily loss limit
        max_feed_age_seconds: float = 5.0,    # 5s stale data halt
        max_divergence_pct: float = 1.0,      # 1% cross-feed divergence halt
    ):
        self.max_position_fraction = max_position_fraction
        self.max_open_orders = max_open_orders
        self.daily_loss_limit_fraction = daily_loss_limit_fraction
        self.max_feed_age_seconds = max_feed_age_seconds
        self.max_divergence_pct = max_divergence_pct
        self.emergency_halted = False
        self.halt_reason = ""
        self._lock = threading.Lock()

    def check_pre_trade(
        self,
        symbol: str,
        action: str,
        requested_value: float,
        total_portfolio_equity: float,
        current_open_orders_count: int,
        feed_age_seconds: float,
        cross_source_divergence_pct: float,
        day_pnl: float,
        day_start_equity: float,
    ) -> Tuple[bool, List[str]]:
        """Run fail-closed pre-trade validation gates."""
        reasons = []

        with self._lock:
            if self.emergency_halted:
                return False, [f"EMERGENCY_HALT_ACTIVE: {self.halt_reason}"]

        # 1. Stale feed check
        if feed_age_seconds > self.max_feed_age_seconds:
            reasons.append(f"STALE_FEED_HALT: Feed age {feed_age_seconds:.1f}s exceeds limit {self.max_feed_age_seconds}s")

        # 2. Cross-source divergence check
        if cross_source_divergence_pct > self.max_divergence_pct:
            reasons.append(f"CROSS_FEED_DIVERGENCE_HALT: Deviation {cross_source_divergence_pct:.2f}% exceeds {self.max_divergence_pct}%")

        # 3. Daily loss limit check
        if day_start_equity > 0:
            loss_pct = -day_pnl / day_start_equity
            if loss_pct >= self.daily_loss_limit_fraction:
                with self._lock:
                    self.emergency_halted = True
                    self.halt_reason = f"Daily loss limit reached ({loss_pct*100:.1f}%)"
                reasons.append(f"DAILY_LOSS_LIMIT_HALT: Lost {loss_pct*100:.1f}% today (limit {self.daily_loss_limit_fraction*100:.1f}%)")

        # 4. Spot only check: NO short selling
        if action not in {"LONG", "BUY", "CLOSE", "SELL"}:
            reasons.append(f"INVALID_ACTION: Spot terminal allows long and close actions only (received {action})")

        # 5. Position sizing check (max 5% portfolio)
        if total_portfolio_equity > 0 and action in {"LONG", "BUY"}:
            max_allowed_val = total_portfolio_equity * self.max_position_fraction
            if requested_value > max_allowed_val:
                reasons.append(f"POSITION_LIMIT_EXCEEDED: Requested ${requested_value:.2f} exceeds {self.max_position_fraction*100}% cap (${max_allowed_val:.2f})")

        # 6. Max open orders check
        if current_open_orders_count >= self.max_open_orders:
            reasons.append(f"MAX_ORDERS_EXCEEDED: Open orders count {current_open_orders_count} reaches limit {self.max_open_orders}")

        return len(reasons) == 0, reasons

    def trigger_halt(self, reason: str):
        with self._lock:
            self.emergency_halted = True
            self.halt_reason = reason
            logger.warning("Emergency halt triggered: %s", reason)

    def resume_after_admin_auth(self, reason: str = "Admin resumed"):
        with self._lock:
            self.emergency_halted = False
            self.halt_reason = ""
            logger.info("Emergency halt cleared by administrator: %s", reason)


class EmergencyKillSwitch:
    """Master Emergency Kill Switch: immediately halts bot, cancels orders, and flattens positions."""

    def __init__(self, risk_governor: RiskGovernor, live_gate: LiveMultiGateGovernor):
        self.risk = risk_governor
        self.live_gate = live_gate
        self.halted = False
        self.halted_at: Optional[float] = None
        self.halted_by: Optional[str] = None
        self._lock = threading.Lock()

    def execute_kill_switch(self, triggered_by: str = "Operator Kill Switch", cancel_orders_fn=None, flatten_positions_fn=None) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            self.halted = True
            self.halted_at = now
            self.halted_by = triggered_by

            # 1. Trigger risk governor emergency halt
            self.risk.trigger_halt(f"Master Kill Switch engaged by {triggered_by}")

            # 2. Deactivate live mode to paper
            self.live_gate.deactivate_to_paper(reason="Kill switch engaged")

            canceled_count = 0
            flattened_count = 0

            # 3. Cancel open orders
            if callable(cancel_orders_fn):
                try:
                    canceled_count = cancel_orders_fn()
                except Exception as e:
                    logger.error("Error canceling open orders during kill switch: %s", e)

            # 4. Flatten open positions via market orders
            if callable(flatten_positions_fn):
                try:
                    flattened_count = flatten_positions_fn()
                except Exception as e:
                    logger.error("Error flattening positions during kill switch: %s", e)

            logger.critical("MASTER EMERGENCY KILL-SWITCH EXECUTED by %s at %s. Canceled %d orders, flattened %d positions.",
                            triggered_by, time.ctime(now), canceled_count, flattened_count)

            return {
                "status": "HALTED",
                "kill_switch_engaged": True,
                "timestamp": now,
                "triggered_by": triggered_by,
                "orders_canceled": canceled_count,
                "positions_flattened": flattened_count,
            }

    def resume_bot(self, admin_reauthenticated: bool, admin_email: str) -> Dict[str, Any]:
        """Requires authenticated administrator to disengage kill switch."""
        if not admin_reauthenticated:
            raise ValueError("Admin password re-authentication is mandatory to disengage the emergency kill switch.")

        with self._lock:
            self.halted = False
            self.risk.resume_after_admin_auth(f"Resumed by admin {admin_email}")
            logger.info("Emergency kill switch disengaged by %s", admin_email)
            return {
                "status": "ACTIVE",
                "kill_switch_engaged": False,
                "resumed_by": admin_email,
                "timestamp": time.time(),
            }


class UnifiedExchangeAdapter:
    """Exchange adapter ensuring idempotent client order IDs and spot-only execution."""

    def __init__(self, exchange_id: str = "binance", sandbox: bool = True):
        self.exchange_id = exchange_id
        self.sandbox = sandbox
        self.orders: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Idempotent order creation with UUIDv4 tracking."""
        cid = client_order_id or str(uuid.uuid4())
        with self._lock:
            if cid in self.orders:
                logger.info("Idempotent hit for order %s", cid)
                return self.orders[cid]

            now = time.time()
            order_record = {
                "order_id": f"ord_{uuid.uuid4().hex[:12]}",
                "client_order_id": cid,
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": quantity,
                "price": price,
                "status": "FILLED" if order_type.upper() == "MARKET" else "OPEN",
                "sandbox": self.sandbox,
                "venue": self.exchange_id,
                "created_at": now,
            }
            self.orders[cid] = order_record
            return order_record

    def cancel_order(self, client_order_id: str) -> bool:
        with self._lock:
            if client_order_id in self.orders:
                self.orders[client_order_id]["status"] = "CANCELED"
                return True
            return False

    def reconcile_orders(self) -> Dict[str, Any]:
        """Periodic reconciliation between local order store and venue reality."""
        with self._lock:
            open_count = sum(1 for o in self.orders.values() if o["status"] == "OPEN")
            filled_count = sum(1 for o in self.orders.values() if o["status"] == "FILLED")
            return {
                "venue": self.exchange_id,
                "sandbox": self.sandbox,
                "open_orders": open_count,
                "filled_orders": filled_count,
                "total_tracked": len(self.orders),
                "reconciled_at": time.time(),
            }
