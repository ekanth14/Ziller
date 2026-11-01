"""Tests for Risk Governor, 5-Gate Live Trading Gatekeeper, and Emergency Kill Switch."""
import os
import time
import unittest
from unittest.mock import patch

from cryptoscope.execution.governor import (
    LiveMultiGateGovernor,
    LiveGateError,
    RiskGovernor,
    EmergencyKillSwitch,
    UnifiedExchangeAdapter,
)


class GovernorTests(unittest.TestCase):
    def test_default_mode_is_paper(self):
        live_gov = LiveMultiGateGovernor()
        self.assertEqual(live_gov.mode, "PAPER")

    def test_live_trading_blocked_if_any_gate_fails(self):
        live_gov = LiveMultiGateGovernor()
        now = time.time()

        # Test Case 1: LIVE_TRADING env var not set
        with patch.dict(os.environ, {}, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=100,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 1 Failed" in r for r in reasons))

        # Test Case 2: Missing API Keys
        with patch.dict(os.environ, {"LIVE_TRADING": "true"}, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=100,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 2 Failed" in r for r in reasons))

        # Test Case 3: Less than 50 paper trades
        env = {"LIVE_TRADING": "true", "EXCHANGE_API_KEY": "key123", "EXCHANGE_API_SECRET": "sec456"}
        with patch.dict(os.environ, env, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=35,
                paper_net_pnl=200.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 3 Failed" in r for r in reasons))

        # Test Case 4: Negative paper PnL
        with patch.dict(os.environ, env, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=80,
                paper_net_pnl=-50.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 3 Failed" in r for r in reasons))

        # Test Case 5: Expired admin re-auth (>300s)
        with patch.dict(os.environ, env, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=80,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now - 400,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 4 Failed" in r for r in reasons))

        # Test Case 6: Typo in confirmation string
        with patch.dict(os.environ, env, clear=True):
            passed, reasons = live_gov.verify_gates(
                paper_trade_count=80,
                paper_net_pnl=500.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="enable live",
                now=now,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Gate 5 Failed" in r for r in reasons))

    def test_live_trading_activates_only_when_all_5_gates_pass(self):
        live_gov = LiveMultiGateGovernor()
        now = time.time()
        env = {"LIVE_TRADING": "true", "EXCHANGE_API_KEY": "valid_key", "EXCHANGE_API_SECRET": "valid_secret"}
        with patch.dict(os.environ, env, clear=True):
            live_gov.activate_live(
                paper_trade_count=65,
                paper_net_pnl=1250.0,
                admin_reauthenticated=True,
                admin_reauth_time=now,
                typed_confirmation="ENABLE LIVE TRADING",
                now=now,
            )
            self.assertEqual(live_gov.mode, "LIVE")

            # Deactivate back to paper
            live_gov.deactivate_to_paper("Testing return to paper")
            self.assertEqual(live_gov.mode, "PAPER")

    def test_risk_governor_pre_trade_gates(self):
        risk = RiskGovernor(
            max_position_fraction=0.05,
            max_feed_age_seconds=5.0,
            max_divergence_pct=1.0,
            daily_loss_limit_fraction=0.03,
        )

        # 1. Stale feed halts trade
        allowed, reasons = risk.check_pre_trade(
            symbol="BTCUSDT",
            action="LONG",
            requested_value=200.0,
            total_portfolio_equity=10000.0,
            current_open_orders_count=0,
            feed_age_seconds=7.5,  # > 5.0s
            cross_source_divergence_pct=0.2,
            day_pnl=0.0,
            day_start_equity=10000.0,
        )
        self.assertFalse(allowed)
        self.assertTrue(any("STALE_FEED_HALT" in r for r in reasons))

        # 2. Cross-feed divergence >1% halts trade
        allowed, reasons = risk.check_pre_trade(
            symbol="BTCUSDT",
            action="LONG",
            requested_value=200.0,
            total_portfolio_equity=10000.0,
            current_open_orders_count=0,
            feed_age_seconds=1.0,
            cross_source_divergence_pct=1.4,  # > 1.0%
            day_pnl=0.0,
            day_start_equity=10000.0,
        )
        self.assertFalse(allowed)
        self.assertTrue(any("CROSS_FEED_DIVERGENCE_HALT" in r for r in reasons))

        # 3. Position limit exceeded (>5% of 10,000 = $500 max)
        allowed, reasons = risk.check_pre_trade(
            symbol="BTCUSDT",
            action="LONG",
            requested_value=800.0,  # $800 > $500
            total_portfolio_equity=10000.0,
            current_open_orders_count=0,
            feed_age_seconds=1.0,
            cross_source_divergence_pct=0.1,
            day_pnl=0.0,
            day_start_equity=10000.0,
        )
        self.assertFalse(allowed)
        self.assertTrue(any("POSITION_LIMIT_EXCEEDED" in r for r in reasons))

        # 4. Valid trade passes
        allowed, reasons = risk.check_pre_trade(
            symbol="BTCUSDT",
            action="LONG",
            requested_value=400.0,
            total_portfolio_equity=10000.0,
            current_open_orders_count=1,
            feed_age_seconds=1.2,
            cross_source_divergence_pct=0.05,
            day_pnl=50.0,
            day_start_equity=10000.0,
        )
        self.assertTrue(allowed)
        self.assertEqual(len(reasons), 0)

    def test_emergency_kill_switch_execution_and_admin_resume(self):
        risk = RiskGovernor()
        live_gov = LiveMultiGateGovernor()
        ks = EmergencyKillSwitch(risk, live_gov)

        canceled = []
        flattened = []

        def cancel_all():
            canceled.append("all_orders")
            return 3

        def flatten_all():
            flattened.append("all_positions")
            return 2

        res = ks.execute_kill_switch("Risk Manager", cancel_all, flatten_all)
        self.assertEqual(res["status"], "HALTED")
        self.assertTrue(res["kill_switch_engaged"])
        self.assertEqual(res["orders_canceled"], 3)
        self.assertEqual(res["positions_flattened"], 2)
        self.assertTrue(ks.halted)
        self.assertTrue(risk.emergency_halted)

        # Pre-trade check fails closed while halted
        allowed, _ = risk.check_pre_trade("BTCUSDT", "LONG", 100, 10000, 0, 1, 0, 0, 10000)
        self.assertFalse(allowed)

        # Resume requires admin re-authentication
        with self.assertRaises(ValueError):
            ks.resume_bot(admin_reauthenticated=False, admin_email="admin@zillers.local")

        resume_res = ks.resume_bot(admin_reauthenticated=True, admin_email="admin@zillers.local")
        self.assertEqual(resume_res["status"], "ACTIVE")
        self.assertFalse(ks.halted)
        self.assertFalse(risk.emergency_halted)

    def test_unified_exchange_adapter_idempotency(self):
        adapter = UnifiedExchangeAdapter(exchange_id="binance", sandbox=True)
        cid = "custom-client-order-uuid-12345"
        o1 = adapter.create_order("BTCUSDT", "BUY", "LIMIT", 0.5, 68000.0, client_order_id=cid)
        o2 = adapter.create_order("BTCUSDT", "BUY", "LIMIT", 0.5, 68000.0, client_order_id=cid)
        self.assertEqual(o1["order_id"], o2["order_id"])
        self.assertEqual(len(adapter.orders), 1)

        recon = adapter.reconcile_orders()
        self.assertEqual(recon["total_tracked"], 1)


if __name__ == "__main__":
    unittest.main()
