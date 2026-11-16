"""ExecutionBot: Order routing, exchange-level stop loss, supervisor watchdog, and state persistence."""

import asyncio
from contextlib import closing
import json
import hashlib
import logging
import math
from pathlib import Path
import sqlite3
from cryptoscope.storage.sqlite import connect_database
from cryptoscope.execution.lifecycle import TestnetLifecycle
import time
from typing import Any, Dict, List, Optional

from cryptoscope.orchestrator.base_bot import BaseBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import (
    BaseEvent,
    Fill,
    MarketUpdate,
    OrderRequest,
    PositionClosed,
    RiskDecision,
    SupervisorHeartbeat,
    SystemAlert,
    TradeIntent,
)
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.execution.governor import LiveMultiGateGovernor, RiskGovernor
from cryptoscope.execution.binance_testnet import (
    BinanceTestnetClient,
    BinanceClientError,
    BinanceAuthError,
    BinanceOrderFilterError,
    BinanceInsufficientBalanceError,
)

logger = logging.getLogger("cryptoscope.orchestrator.execution_bot")


class ExecutionBot(TestnetLifecycle,BaseBot):
    """The SOLE bot permitted to import broker and exchange clients.

    Responsible for:
    1. Placing entry orders in OBSERVE, PAPER, TESTNET, or LIVE modes.
    2. Placing exchange-level stop-loss orders immediately upon entry.
    3. Monitoring SupervisorHeartbeat: if supervisor goes silent (>15s), flattens or protects positions.
    4. Persisting orders and positions in SQLite state store, reconciling on startup.
    5. Enforcing 5-gate live trading governor for LIVE mode.
    """

    def __init__(
        self,
        bus: EventBus,
        name: str = "execution_bot",
        mode: str = "PAPER",  # 'OBSERVE', 'PAPER', 'TESTNET', 'LIVE'
        db_path: Optional[str] = None,
        supervisor_timeout_sec: float = 15.0,
        watchdog_grace_sec: Optional[float] = None,
        exchange_api_key: str = "",
        exchange_api_secret: str = ""
    ):
        super().__init__(name, bus)
        self.mode = mode.upper()
        self.supervisor_timeout_sec = supervisor_timeout_sec
        self.watchdog_grace_sec = (
            watchdog_grace_sec
            if watchdog_grace_sec is not None
            else min(5.0, max(0.01, supervisor_timeout_sec * 0.5))
        )
        self.exchange_api_key = exchange_api_key
        self.exchange_api_secret = exchange_api_secret

        self.last_supervisor_heartbeat = time.time()
        self.watchdog_grace_start: Optional[float] = None
        self.emergency_protection_active = False

        # SQLite state persistence
        self.db_path = Path(db_path or "work/runtime/orchestrator_state.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Paper Broker instance for PAPER mode
        self.paper_broker = PaperBroker(
            path="work/runtime/paper_execution.db",
            config={"initial_cash": 10000.0, "fee_fraction": 0.001, "slippage_fraction": 0.0005}
        )
        self.live_governor = LiveMultiGateGovernor(mode=self.mode)

        # Binance Spot Testnet client for TESTNET mode
        self.binance_client = BinanceTestnetClient(
            api_key=self.exchange_api_key,
            api_secret=self.exchange_api_secret,
        )

        # In-memory working positions & orders
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self.cached_intents: Dict[str, TradeIntent] = {}
        self.last_exchange_reconciliation = 0.0
        self.last_emergency_poll = 0.0

        # Every halt raises a CRITICAL alert (deduplicated), whichever code path triggered it
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_halt_alert: Dict[str, float] = {}
        self.halt_state.add_listener(self._on_halt)

        # Reconcile on startup
        self.reconcile_state()

        self.subscribe(RiskDecision)
        self.subscribe(TradeIntent)
        self.subscribe(SupervisorHeartbeat)
        self.subscribe(MarketUpdate)

    def _on_halt(self, snapshot: Dict[str, Any]) -> None:
        """Publish a CRITICAL SystemAlert for a durable halt (thread-safe, 60s per-reason dedup)."""
        reason = str(snapshot.get('reason', ''))
        now = time.time()
        if now - self._last_halt_alert.get(reason, 0.0) < 60.0:
            return
        self._last_halt_alert[reason] = now
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        alert = SystemAlert(
            severity="CRITICAL",
            source=self.name,
            title="Trading halted",
            message=f"{snapshot.get('action', 'HALT')}: {reason}",
            details={"actor": snapshot.get('actor'), "mode": self.mode},
        )
        try:
            asyncio.run_coroutine_threadsafe(self.emit(alert), loop)
        except Exception:
            logger.exception("[%s] failed to schedule halt alert", self.name)

    async def start(self):
        self._loop = asyncio.get_running_loop()
        if self.mode=='TESTNET':
            await asyncio.to_thread(self.reconcile_uncertain_entries)
            await asyncio.to_thread(self.reconcile_testnet_positions)
        await super().start()

    def reconcile_testnet_positions(self):
        """Read exchange protection on restart/periodically.

        - Stop FILLED while offline: the fill is booked and the position closed.
        - Stop missing/cancelled/expired: protection is repaired automatically (adopt, place, or
          close if price is already through the stop). The durable halt latch is never cleared.
        - Anything else that does not match the owned protection halts for reconciliation.
        """
        self.last_exchange_reconciliation=time.time()
        for symbol,pos in list(self.active_positions.items()):
            try:
                if pos.get('mode')!='TESTNET':raise ValueError()
                reference=pos.get('stop_order_id')
                if not str(reference).isdigit():
                    self._repair_or_close(symbol,pos);continue
                order=self.binance_client.get_order(symbol=symbol,order_id=int(reference))
                status=order.get('status')
                if status=='FILLED':
                    actual=self.book_filled_stop(symbol,pos,order)
                    if actual is not None:self._finalize_closed_position(symbol,pos,'STOP_LOSS',actual)
                    continue
                if status in {'CANCELED','EXPIRED','EXPIRED_IN_MATCH','REJECTED'} and float(order.get('executedQty',0))==0:
                    pos['stop_order_id']=None;self._save_position_db(pos)
                    self._repair_or_close(symbol,pos);continue
                if (order.get('symbol')!=symbol or order.get('side')!='SELL' or status!='NEW'
                    or order.get('type') not in {'STOP_LOSS','STOP_LOSS_LIMIT'}
                    or abs(float(order.get('origQty',0))-pos.get('protected_quantity',pos['quantity']))>1e-9
                    or float(order.get('executedQty',0))!=0):raise ValueError()
            except Exception:
                self.halt_state.halt('Exchange protection mismatch; reconciliation required',self.name)

    def _repair_or_close(self,symbol,pos):
        outcome,exit_price=self.repair_protection(symbol,pos)
        if outcome=='CLOSED':
            self._finalize_closed_position(symbol,pos,'STOP_LOSS',exit_price)
        else:
            logger.warning('[%s] Exchange protection %s for %s; durable halt retained for review',self.name,outcome.lower(),symbol)

    def _finalize_closed_position(self,sym,pos,exit_reason,exit_price):
        """Book a confirmed exchange-side close (thread-safe): remove position, publish PositionClosed."""
        entry=pos['entry_price'];qty=pos.get('closed_quantity',pos['quantity'])
        pnl_usd=(exit_price-entry)*qty
        pnl_pct=((exit_price-entry)/entry)*100.0 if entry else 0.0
        closed=PositionClosed(symbol=sym,side=pos['side'],entry_price=entry,exit_price=exit_price,quantity=qty,
            pnl_usd=round(pnl_usd,2),pnl_pct=round(pnl_pct,2),
            duration_seconds=round(time.time()-pos.get('created_at',time.time()),2),exit_reason=exit_reason,
            commission_by_asset=pos.get('commission_by_asset',{}),fee_valuation_complete=pos.get('fee_valuation_complete',True))
        self.active_positions.pop(sym,None)
        self._remove_position_db(sym)
        logger.warning('[%s] Position %s closed on exchange via %s @ %.4f (PnL $%.2f)',self.name,sym,exit_reason,exit_price,pnl_usd)
        loop=self._loop
        if loop is not None and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.emit(closed),loop)

    def _init_db(self) -> None:
        """Initialize SQLite tables for persistent state reconciliation."""
        conn = connect_database(str(self.db_path))
        try:
            if conn.execute('PRAGMA user_version').fetchone()[0]>2:
                raise RuntimeError('Execution database schema is newer than this application')
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    target_price REAL NOT NULL,
                    stop_order_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    intent_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            if 'mode' not in [r[1] for r in conn.execute('PRAGMA table_info(positions)')]:
                conn.execute("ALTER TABLE positions ADD COLUMN mode TEXT NOT NULL DEFAULT 'UNKNOWN'")
            conn.execute('CREATE TABLE IF NOT EXISTS position_details(symbol TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS exchange_observations(reference TEXT PRIMARY KEY,symbol TEXT NOT NULL,payload TEXT NOT NULL,updated_at REAL NOT NULL)')
            if conn.execute('PRAGMA user_version').fetchone()[0]<2:
                conn.execute('PRAGMA user_version=2')
            conn.commit()
        finally:
            conn.close()

    def reconcile_state(self) -> None:
        """Reconcile persisted positions and orders on startup."""
        conn = connect_database(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM positions").fetchall()
            for r in rows:
                self.active_positions[r["symbol"]] = {
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "quantity": float(r["quantity"]),
                    "entry_price": float(r["entry_price"]),
                    "stop_price": float(r["stop_price"]),
                    "target_price": float(r["target_price"]),
                    "stop_order_id": r["stop_order_id"],
                    "created_at": r['created_at'],
                    'mode':r['mode'],
                }
            for symbol,payload in conn.execute('SELECT symbol,payload FROM position_details'):
                if symbol in self.active_positions:self.active_positions[symbol].update(json.loads(payload))
            pending=conn.execute("SELECT * FROM orders WHERE status='RECONCILE_REQUIRED'").fetchall()
            for row in pending:
                self.active_orders[row['order_id']]=dict(row)
                if row['order_id'].startswith('close_') and row['symbol'] in self.active_positions:
                    self.active_positions[row['symbol']]['exit_client_id']=row['order_id']
            if self.mode=='TESTNET' and (pending or any(p.get('mode')!='TESTNET' or not str(p.get('stop_order_id','')).isdigit() for p in self.active_positions.values())):
                self.halt_state.halt('Persisted exchange exposure requires reconciliation',self.name)
            logger.info("[%s] State reconciled: %d active positions loaded.", self.name, len(self.active_positions))
        finally:
            conn.close()

    def _save_position_db(self, pos: Dict[str, Any]) -> None:
        conn = connect_database(str(self.db_path))
        try:
            conn.execute("""
                INSERT OR REPLACE INTO positions 
                (symbol, side, quantity, entry_price, stop_price, target_price, stop_order_id, created_at, updated_at, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pos["symbol"], pos["side"], pos["quantity"], pos["entry_price"],
                pos["stop_price"], pos["target_price"], pos.get("stop_order_id"),
                pos.get("created_at", time.time()), time.time(),pos.get('mode',self.mode)
            ))
            conn.execute('INSERT INTO position_details VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET payload=excluded.payload',(pos['symbol'],json.dumps(pos,allow_nan=False)))
            conn.commit()
        finally:
            conn.close()

    def _remove_position_db(self, symbol: str) -> None:
        conn = connect_database(str(self.db_path))
        try:
            conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            conn.commit()
        finally:
            conn.close()

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, TradeIntent):
            self.cached_intents[event.intent_id] = event
        elif isinstance(event, SupervisorHeartbeat):
            self.last_supervisor_heartbeat = time.time()
            if self.watchdog_grace_start is not None:
                logger.info(
                    "[%s] Supervisor heartbeat recovered within grace period (%.2fs). Stops preserved.",
                    self.name, time.time() - self.watchdog_grace_start
                )
                self.watchdog_grace_start = None
            if self.emergency_protection_active:
                logger.info("[%s] Supervisor heartbeat restored. Disengaging emergency protection.", self.name)
                self.emergency_protection_active = False
        elif isinstance(event, RiskDecision):
            if event.decision == "APPROVED":
                await self._execute_approved_trade(event)
        elif isinstance(event, MarketUpdate):
            await self._check_position_exits(event)

    async def _execute_approved_trade(self, risk: RiskDecision) -> None:
        if self.halt_state.snapshot()['halted']:
            return
        intent = self.cached_intents.get(risk.intent_id)
        if not intent:
            logger.warning("[%s] Cannot execute: missing TradeIntent for %s", self.name, risk.intent_id)
            return

        symbol = risk.symbol
        side = intent.direction
        qty = risk.approved_quantity
        price = intent.entry_price
        if symbol != intent.symbol:
            self.halt_state.halt('Approved symbol conflicts with trade intent',self.name)
            return

        # Mode check
        if self.mode == "OBSERVE":
            logger.info("[%s] [OBSERVE MODE] Logged trade: %s %s qty=%.4f @ %.4f (No order placed)", self.name, side, symbol, qty, price)
            return

        if self.mode == "LIVE":
            if self.live_governor.mode != "LIVE":
                logger.critical("[%s] LIVE MODE BLOCKED: 5-Gate governor has not authorized live trading!", self.name)
                await self.emit(SystemAlert(
                    severity="CRITICAL",
                    source=self.name,
                    title="Live Trading Blocked",
                    message="Refusing order: 5-Gate governor conditions not satisfied."
                ))
                return

        # Prepare OrderRequest
        order = OrderRequest(
            intent_id=intent.intent_id,
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=qty,
            price=price,
            stop_price=intent.stop_loss,
            take_profit_price=intent.take_profit,
            mode=self.mode
        )
        await self.emit(order)

        # A halt may have arrived while subscribers processed OrderRequest.
        if self.halt_state.snapshot()['halted']:
            return

        try:
            executed_price = price
            stop_order_id = None if self.mode == 'TESTNET' else f"paper_stop_{int(time.time()*1000)}"

            # Check mock order executor hook if set for failure injection testing
            if self.mode=="PAPER" and hasattr(self, "_test_order_executor") and self._test_order_executor:
                res = self._test_order_executor(order)
                if not res.get("success", True):
                    raise RuntimeError(res.get("error", "Exchange rejected order: Insufficient balance or invalid lot"))
                qty = res.get("filled_qty", qty)
                price = res.get("executed_price", price)
                executed_price = price
            elif self.mode == "TESTNET":
                testnet_position=self._testnet_entry(intent,qty)
                qty=testnet_position['quantity'];executed_price=testnet_position['entry_price']
                stop_order_id=testnet_position.get('stop_order_id')

            # Execute Entry Order accounting
            fee = testnet_position.get('commission_by_asset',{}).get(testnet_position['quote_asset'],0.) if self.mode=='TESTNET' else qty * executed_price * 0.001
            fill_id = f"fill_{int(time.time()*1000)}"

            # Place exchange-level protective stop-loss order
            if stop_order_id is not None:
                logger.info('[%s] Protective order reference recorded for %s',self.name,symbol)

            fill = Fill(
                fill_id=fill_id,
                order_id=order.order_id,
                client_order_id=f"cli_{intent.intent_id}",
                symbol=symbol,
                side=side,
                quantity=qty,
                executed_price=executed_price,
                fee=fee,
                fee_asset="USDT",
                mode=self.mode,
                stop_order_id=stop_order_id,
                commission_by_asset=testnet_position.get('commission_by_asset',{}) if self.mode=='TESTNET' else {},
                fee_valuation_complete=testnet_position.get('fee_valuation_complete',True) if self.mode=='TESTNET' else True
            )

            # Update position state
            pos_data = {
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "entry_price": executed_price,
                "stop_price": intent.stop_loss,
                "target_price": intent.take_profit,
                "stop_order_id": stop_order_id,
                "created_at": time.time(),
                'mode':self.mode,
            }
            if self.mode=='TESTNET':pos_data.update(testnet_position)
            self.active_positions[symbol] = pos_data
            self._save_position_db(pos_data)


            logger.info("[%s] FILLED: %s %s qty=%.4f @ %.4f. Stop: %.4f, Target: %.4f", self.name, side, symbol, qty, executed_price, intent.stop_loss, intent.take_profit)
            await self.emit(fill)

        except Exception as exc:
            if self.mode=='TESTNET':self.halt_state.halt('Exchange entry unresolved; reconciliation required',self.name)
            logger.error("[%s] Order execution failed / rejected: %s", self.name, exc)
            await self.emit(SystemAlert(
                severity="ERROR",
                source=self.name,
                title="Exchange Order Rejected",
                message=str(exc),
                details={"symbol": symbol, "intent_id": intent.intent_id}
            ))

    def _record_uncertain_order(self,intent_id,symbol,side,order_id,quantity,order_type='MARKET'):
        with closing(connect_database(str(self.db_path))) as db:
            inserted=db.execute('INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (str(order_id or 'entry_'+intent_id),intent_id,symbol,side,order_type,quantity,
                 None,None,'RECONCILE_REQUIRED',self.mode,time.time()))
            db.commit()
            return inserted.rowcount==1

    async def _check_position_exits(self, update: MarketUpdate) -> None:
        """Check active positions against current prices for stop-loss or take-profit hits."""
        if self.mode=='TESTNET' and self.halt_state.snapshot()['halted']:
            return
        sym = update.symbol
        if sym not in self.active_positions:
            return

        pos = self.active_positions[sym]
        curr_price = update.price
        if not math.isfinite(curr_price) or curr_price<=0:
            return
        side = pos["side"]
        entry = pos["entry_price"]
        stop = pos["stop_price"]
        target = pos["target_price"]
        qty = pos["quantity"]

        exit_triggered = False
        exit_reason = ""
        exit_price = curr_price

        if side == "BUY":
            if curr_price <= stop:
                exit_triggered = True
                exit_reason = "STOP_LOSS"
                exit_price = stop
            elif curr_price >= target:
                exit_triggered = True
                exit_reason = "TAKE_PROFIT"
                exit_price = target
        elif side == "SELL":
            if curr_price >= stop:
                exit_triggered = True
                exit_reason = "STOP_LOSS"
                exit_price = stop
            elif curr_price <= target:
                exit_triggered = True
                exit_reason = "TAKE_PROFIT"
                exit_price = target

        if exit_triggered:
            if self.mode=='TESTNET':
                actual=self._confirmed_testnet_close(sym,pos)
                if actual is None:return
                exit_price=actual
                qty=pos.get('closed_quantity',qty)
            pnl_usd = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
            if self.mode != 'TESTNET':
                # software modes: subtract the same 0.1% fee used for entry accounting on both legs
                pnl_usd -= 0.001 * (entry * qty + exit_price * qty)
            pnl_pct = ((exit_price - entry) / entry) * 100.0 if side == "BUY" else ((entry - exit_price) / entry) * 100.0

            closed = PositionClosed(
                symbol=sym,
                side=side,
                entry_price=entry,
                exit_price=exit_price,
                quantity=qty,
                pnl_usd=round(pnl_usd, 2),
                pnl_pct=round(pnl_pct, 2),
                duration_seconds=round(time.time() - pos.get("created_at", time.time()), 2),
                exit_reason=exit_reason,
                commission_by_asset=pos.get('commission_by_asset',{}),fee_valuation_complete=pos.get('fee_valuation_complete',True)
            )
            self.active_positions.pop(sym, None)
            self._remove_position_db(sym)
            logger.info("[%s] Position %s CLOSED via %s @ %.4f (PnL: $%.2f, %.2f%%)", self.name, sym, exit_reason, exit_price, pnl_usd, pnl_pct)
            await self.emit(closed)

    async def emergency_protect_positions(self, reason: str) -> None:
        """Trigger emergency position protection when supervisor heartbeat is lost."""
        self.halt_state.halt(reason, self.name)
        self.emergency_protection_active = True
        logger.critical("[%s] EMERGENCY PROTECTION TRIGGERED: %s", self.name, reason)

        await self.emit(SystemAlert(
            severity="CRITICAL",
            source=self.name,
            title="Supervisor Lost: Emergency Protection Active",
            message=reason,
            details={"active_positions": list(self.active_positions.keys())}
        ))

        # Tighten stops to break-even or flatten positions
        for sym, pos in list(self.active_positions.items()):
            if self.mode=='TESTNET':
                # Existing exchange protection is retained. A software price
                # change is not an exchange stop modification.
                continue
            logger.warning("[%s] Emergency protective action on %s: tightening stop to entry @ %.4f", self.name, sym, pos["entry_price"])
            pos["stop_price"] = pos["entry_price"]
            self._save_position_db(pos)

    async def flatten_all_positions(self, reason: str = "Operator manual flatten") -> int:
        """Immediately market close all open positions."""
        closed_count = 0
        for sym, pos in list(self.active_positions.items()):
            if self.mode == "TESTNET":
                actual=self._confirmed_testnet_close(sym,pos)
                if actual is None:continue
            else:actual=pos['entry_price']

            pnl_usd = 0.0
            closed = PositionClosed(
                symbol=sym,
                side=pos["side"],
                entry_price=pos["entry_price"],
                exit_price=actual,
                quantity=pos.get("closed_quantity",pos["quantity"]),
                pnl_usd=(actual-pos['entry_price'])*pos.get('closed_quantity',pos['quantity'])*(1 if pos['side']=='BUY' else -1),
                pnl_pct=(actual/pos['entry_price']-1)*100*(1 if pos['side']=='BUY' else -1),
                duration_seconds=0.0,
                exit_reason="MANUAL_FLATTEN",
                commission_by_asset=pos.get('commission_by_asset',{}),fee_valuation_complete=pos.get('fee_valuation_complete',True)
            )
            self.active_positions.pop(sym, None)
            self._remove_position_db(sym)
            await self.emit(closed)
            closed_count += 1
        logger.warning("[%s] Flattened %d positions: %s", self.name, closed_count, reason)
        return closed_count

    async def apply_emergency_action(self):
        """Consume the dashboard's durable request; never clear the halt latch.

        The dashboard and fleet may be separate processes. A dashboard response
        is acknowledgement of the request, not proof of an exchange fill.
        Unknown/partial exposure remains halted for manual reconciliation.
        """
        state=self.halt_state.snapshot()
        if state['halted'] and self.mode=='TESTNET':
            # blocking exchange I/O runs off the event loop so heartbeats keep flowing
            await asyncio.to_thread(self.reconcile_uncertain_entries, cancel_working=True)
        if (state['halted'] and state['action']=='HALT_FLATTEN' and
                self.mode in {'PAPER','TESTNET'} and self.active_positions):
            return await self.flatten_all_positions('Durable master HALT_FLATTEN request')
        return 0

    async def run(self) -> None:
        """Watchdog loop checking supervisor heartbeat, applying grace period, and position safety."""
        while self._running:
            self._last_heartbeat = time.time()
            if time.time()-self.last_emergency_poll>=1:
                self.last_emergency_poll=time.time()
                await self.apply_emergency_action()
            if self.mode=='TESTNET' and time.time()-self.last_exchange_reconciliation>=60:
                self.last_exchange_reconciliation=time.time()  # prevents re-entry while the thread runs
                await asyncio.to_thread(self.reconcile_uncertain_entries)
                await asyncio.to_thread(self.reconcile_testnet_positions)
            elapsed = time.time() - self.last_supervisor_heartbeat
            if elapsed > self.supervisor_timeout_sec and not self.emergency_protection_active:
                if self.active_positions:
                    if self.watchdog_grace_start is None:
                        self.watchdog_grace_start = time.time()
                        logger.warning(
                            "[%s] Supervisor silent for %.1fs (threshold %.1fs). "
                            "Entering %.1fs grace period before emergency stop adjustment.",
                            self.name, elapsed, self.supervisor_timeout_sec, self.watchdog_grace_sec
                        )
                    elif (time.time() - self.watchdog_grace_start) >= self.watchdog_grace_sec:
                        await self.emergency_protect_positions(
                            f"Supervisor silent for {elapsed:.1f}s and exceeded grace period of {self.watchdog_grace_sec:.1f}s"
                        )
                        self.watchdog_grace_start = None
            else:
                self.watchdog_grace_start = None
            sleep_interval = min(0.05, max(0.01, self.supervisor_timeout_sec / 4))
            await asyncio.sleep(sleep_interval)

    def get_health_details(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "active_positions_count": len(self.active_positions),
            "emergency_protection_active": self.emergency_protection_active,
            "seconds_since_supervisor_heartbeat": round(time.time() - self.last_supervisor_heartbeat, 1),
            "watchdog_grace_active": self.watchdog_grace_start is not None,
            "watchdog_grace_sec": self.watchdog_grace_sec,
            "halted": self.halt_state.snapshot()['halted'],
            "exchange_cooldown_seconds": max(0.0, round(self.binance_client.retry_after_monotonic - time.monotonic(), 1)),
            "seconds_since_exchange_reconcile": round(time.time() - self.last_exchange_reconciliation, 1),
        }
