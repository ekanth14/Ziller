"""Tests for Risk Governor, 5-Gate Live Trading Gatekeeper, Emergency Kill Switch, and Order Manager."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptoscope.execution.governor import (
    LiveMultiGateGovernor,
    LiveGateError,
    FatalSecurityError,
    RiskGovernor,
    EmergencyKillSwitch,
    UnifiedExchangeAdapter,
    OrderStore,
    AlertService,
)


class GovernorTests(unittest.TestCase):
    def test_default_mode_is_paper(self):
        live_gov = LiveMultiGateGovernor()
        self.assertEqual(live_gov.mode, "PAPER")

    def test_gate3_forward_paper_trading_requirements(self):
        live_gov = LiveMultiGateGovernor()
        now = time.time()
        env = {"LIVE_TRADING": "true", "EXCHANGE_API_KEY": "valid_key", "EXCHANGE_API_SECRET": "valid_secret"}

        with patch.dict(os.environ, env, clear=True):
            # 1. Replayed history fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.08,
                dsr=0.96,
                is_forward_operation=False,  # Replayed history!
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("never replayed history" in r for r in reasons))

            # 2. Less than 28 forward days fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=14.0,  # < 28 days
                max_drawdown=0.08,
                dsr=0.96,
                is_forward_operation=True,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("forward paper days" in r for r in reasons))

            # 3. Less than 100 paper trades fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=45,  # < 100 trades
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.08,
                dsr=0.96,
                is_forward_operation=True,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("forward paper trades" in r for r in reasons))

            # 4. Negative net PnL fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=-50.0,  # Negative
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.08,
                dsr=0.96,
                is_forward_operation=True,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("positive net PnL" in r for r in reasons))

            # 5. Excessive drawdown (>15%) fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.22,  # 22% > 15%
                dsr=0.96,
                is_forward_operation=True,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Maximum drawdown" in r for r in reasons))

            # 6. Low DSR (<0.95) fails Gate 3
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.08,
                dsr=0.90,  # < 0.95
                is_forward_operation=True,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Deflated Sharpe Ratio" in r for r in reasons))

            # 7. Valid forward record passes Gate 3 and all 5 gates
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=120,
                paper_net_pnl=1250.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                forward_days=30.0,
                max_drawdown=0.06,
                dsr=0.97,
                is_forward_operation=True,
                now=now,
            )
            self.assertTrue(passed)
            self.assertEqual(len(reasons), 0)

    def test_gate3_replayed_trades_rejected_by_timestamp_comparison(self):
        live_gov = LiveMultiGateGovernor()
        now = time.time()
        engine_start = now - (30 * 86400)  # Started 30 days ago
        env = {"LIVE_TRADING": "true", "EXCHANGE_API_KEY": "valid_key", "EXCHANGE_API_SECRET": "valid_secret"}

        with patch.dict(os.environ, env, clear=True):
            # Trades containing an old timestamp prior to engine_start -> REJECTED
            replayed_trades = [
                {"buy_time": engine_start + 1000, "post_tax_pnl": 10.0} for _ in range(99)
            ]
            replayed_trades.append({"buy_time": engine_start - 3600, "post_tax_pnl": 15.0})  # Prior to start!

            passed, reasons = live_gov.verify_gates(
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                dsr=0.96,
                engine_start_time=engine_start,
                trades=replayed_trades,
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Replayed historical trades detected" in r for r in reasons))

            # All trades after engine_start -> PASSED
            valid_forward_trades = [
                {"buy_time": engine_start + (i * 1000), "post_tax_pnl": 15.0} for i in range(110)
            ]
            passed, reasons = live_gov.verify_gates(
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                dsr=0.96,
                engine_start_time=engine_start,
                trades=valid_forward_trades,
                now=now,
            )
            self.assertTrue(passed)
            self.assertEqual(len(reasons), 0)
            self.assertTrue(passed)
            self.assertEqual(len(reasons), 0)

    def test_kill_switch_halt_vs_halt_flatten(self):
        risk = RiskGovernor()
        live_gov = LiveMultiGateGovernor()
        ks = EmergencyKillSwitch(risk, live_gov)

        actions_taken = []
        def cancel_fn(keep_stops=False):
            actions_taken.append(f"cancel_orders(keep_stops={keep_stops})")
            return 2

        def flatten_fn():
            actions_taken.append("flatten_positions")
            return 1

        # Action 1: Default HALT (preserves positions and protective stops)
        res1 = ks.execute_kill_switch(action="HALT", triggered_by="Risk Manager", cancel_orders_fn=cancel_fn, flatten_positions_fn=flatten_fn)
        self.assertEqual(res1["status"], "HALTED")
        self.assertEqual(res1["action"], "HALT")
        self.assertEqual(res1["positions_flattened"], 0)
        self.assertIn("cancel_orders(keep_stops=True)", actions_taken)
        self.assertNotIn("flatten_positions", actions_taken)

        # Resume bot
        ks.resume_bot(admin_reauthenticated=True, admin_email="admin@zillers.local")
        actions_taken.clear()

        # Action 2: HALT_FLATTEN (cancels all orders AND flattens positions)
        res2 = ks.execute_kill_switch(action="HALT_FLATTEN", triggered_by="Risk Manager", cancel_orders_fn=cancel_fn, flatten_positions_fn=flatten_fn)
        self.assertEqual(res2["status"], "HALTED")
        self.assertEqual(res2["action"], "HALT_FLATTEN")
        self.assertEqual(res2["positions_flattened"], 1)
        self.assertIn("cancel_orders(keep_stops=False)", actions_taken)
        self.assertIn("flatten_positions", actions_taken)

    def test_order_manager_reconciliation_mismatch_halts(self):
        risk = RiskGovernor()
        alerts = AlertService()
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_exec.db"
            store = OrderStore(db_path)
            adapter = UnifiedExchangeAdapter(order_store=store, risk_governor=risk, alert_service=alerts)

            # Local has order 1
            adapter.create_order("BTCUSDT", "BUY", "LIMIT", 0.5, 68000.0, client_order_id="order-loc-1")

            # Exchange reality has order 1 AND untracked order 2
            aligned, report = adapter.reconcile_with_exchange(["order-loc-1", "order-untracked-2"])
            self.assertFalse(aligned)
            self.assertTrue(risk.emergency_halted)
            self.assertIn("ORDER_RECONCILIATION_MISMATCH", risk.halt_reason)

    def test_protective_stops_and_partial_fills(self):
        risk = RiskGovernor()
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test_exec2.db"
            store = OrderStore(db_path)
            adapter = UnifiedExchangeAdapter(order_store=store, risk_governor=risk)

            # Create a regular limit order and a protective stop order
            limit_ord = adapter.create_order("BTCUSDT", "BUY", "LIMIT", 1.0, 68000.0, client_order_id="limit-1")
            stop_ord = adapter.create_order("BTCUSDT", "SELL", "STOP_LOSS", 1.0, stop_price=65000.0, client_order_id="stop-1")

            self.assertFalse(limit_ord["is_stop"])
            self.assertTrue(stop_ord["is_stop"])

            # Cancel working orders while preserving protective stops
            canceled = adapter.cancel_all_orders(keep_stops=True)
            self.assertEqual(canceled, 1)
            self.assertEqual(adapter.orders["limit-1"]["status"], "CANCELED")
            self.assertEqual(adapter.orders["stop-1"]["status"], "OPEN")

            # Test partial fill execution
            buy_ord = adapter.create_order("ETHUSDT", "BUY", "LIMIT", 10.0, 2500.0, client_order_id="buy-eth-1")
            adapter.fill_order("buy-eth-1", fill_qty=4.0, fill_price=2500.0)
            self.assertEqual(adapter.orders["buy-eth-1"]["status"], "PARTIALLY_FILLED")
            self.assertEqual(adapter.orders["buy-eth-1"]["executed_qty"], 4.0)

            # Complete fill
            adapter.fill_order("buy-eth-1", fill_qty=6.0, fill_price=2500.0)
            self.assertEqual(adapter.orders["buy-eth-1"]["status"], "FILLED")
            self.assertEqual(adapter.orders["buy-eth-1"]["executed_qty"], 10.0)

    def test_withdrawal_permission_disabled_check(self):
        adapter = UnifiedExchangeAdapter()

        # 1. Production / Mock function indicating withdrawals are enabled -> must throw FatalSecurityError
        with self.assertRaises(FatalSecurityError):
            adapter.verify_withdrawal_permissions_disabled("key", "secret", mock_check_fn=lambda k, s: True)

        # 2. Production / Mock function indicating withdrawals are disabled -> succeeds
        self.assertTrue(adapter.verify_withdrawal_permissions_disabled("key", "secret", mock_check_fn=lambda k, s: False))

        # 3. Testnet sandbox behavior in PAPER mode -> logs warning and returns False
        with self.assertLogs("cryptoscope.execution.governor", level="WARNING") as cm:
            result = adapter.verify_withdrawal_permissions_disabled("test_key", "test_secret", is_live_mode=False)
            self.assertFalse(result)
            self.assertTrue(any("withdrawal check NOT verifiable" in m for m in cm.output))

        # 4. Testnet sandbox behavior in LIVE mode -> strictly BLOCKS LIVE mode
        with self.assertRaises(FatalSecurityError):
            adapter.verify_withdrawal_permissions_disabled("test_key", "test_secret", is_live_mode=True)

        # 5. Endpoint cannot report permissions (unverifiable) in LIVE mode -> strictly BLOCKS LIVE mode
        with self.assertRaises(FatalSecurityError):
            adapter.verify_withdrawal_permissions_disabled(
                "key", "secret", mock_check_fn=lambda k, s: "UNVERIFIABLE", is_live_mode=True
            )

    def test_risk_governor_additional_limits(self):
        risk = RiskGovernor(
            symbol_allowlist=["BTCUSDT", "ETHUSDT"],
            loss_cooldown_seconds=600.0,
            max_trades_per_day=5,
            total_drawdown_limit_fraction=0.10,
        )
        now = time.time()

        # 1. Unapproved symbol rejected
        allowed, reasons = risk.check_pre_trade("DOGEUSDT", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now)
        self.assertFalse(allowed)
        self.assertTrue(any("SYMBOL_NOT_ALLOWED" in r for r in reasons))

        # 2. Approved symbol passes
        allowed, reasons = risk.check_pre_trade("BTCUSDT", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now)
        self.assertTrue(allowed)

        # 3. Post-loss cooldown blocks new entries
        risk.record_trade_completion(pnl=-150.0, current_equity=9850.0, now=now)
        allowed, reasons = risk.check_pre_trade("BTCUSDT", "BUY", 100, 9850, 0, 1.0, 0.1, 0, 10000, now=now + 100)
        self.assertFalse(allowed)
        self.assertTrue(any("LOSS_COOLDOWN_ACTIVE" in r for r in reasons))

        # After cooldown expires, entries are permitted
        allowed, _ = risk.check_pre_trade("BTCUSDT", "BUY", 100, 9850, 0, 1.0, 0.1, 0, 10000, now=now + 700)
        self.assertTrue(allowed)

        # 4. Total drawdown limit (peak 10,000, drops to 8,800 -> 12% drawdown > 10% limit)
        risk.peak_equity = 10000.0
        allowed, reasons = risk.check_pre_trade("BTCUSDT", "BUY", 100, 8800.0, 0, 1.0, 0.1, 0, 10000, now=now + 700)
        self.assertFalse(allowed)
        self.assertTrue(any("TOTAL_DRAWDOWN_HALT" in r for r in reasons))
        self.assertTrue(risk.emergency_halted)


    def test_token_safety_audit_rejects_danger_tokens(self):
        risk = RiskGovernor(max_position_fraction=0.10)
        now = 1700000000.0

        # Safe token passes
        allowed, reasons = risk.check_pre_trade(
            "BTCUSDT", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now,
            token_audit={"band": "CLEAN", "score": 92}
        )
        self.assertTrue(allowed)

        # Danger token rejected
        allowed, reasons = risk.check_pre_trade(
            "SCAMCOIN", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now,
            token_audit={"band": "DANGER", "score": 25}
        )
        self.assertFalse(allowed)
        self.assertTrue(any("ONCHAIN_SAFETY_FAIL" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
