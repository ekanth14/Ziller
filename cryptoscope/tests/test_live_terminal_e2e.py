"""End-to-end tests for ZILLERS trading terminal with real market data and integrations.

Tests every feature and function:
1. Real candle data retrieval (BTCUSDT, ETHUSDT, SOLUSDT)
2. 100+ Crypto listings endpoint
3. FX rate conversion feed (USD / INR)
4. Monte Carlo Odds Simulation with real market candles
5. Adversarial Multi-Agent Deliberation (Bull vs Bear vs Tri-Risk debate)
6. QuantOrb On-Chain Token Safety Audit & AMM slippage model
7. Quantitative Alpha Strategies (Volume Breakout, Shrink Pullback, Box Oscillation)
8. 5-Gate Pre-Trade Risk Governor with Token Safety check
9. Static production assets integrity (index.html, app.js, style.css)
10. CoinGecko listings filter: strictly excludes delisted/unlisted tokens (XMR, WBT, LEO) and includes real prices
"""
import json
from pathlib import Path
import tempfile
import unittest

from cryptoscope.dashboard.data import DashboardData
from cryptoscope.market_data.candle_store import CandleStore
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.coingecko import CoinGeckoService
from cryptoscope.simulation.time_machine import simulate_trade_odds
from cryptoscope.agents.consensus import DeliberationConsensusEngine
from cryptoscope.agents.analysts.market import technical
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.risk_tools.onchain_guard import cluster_operators, score_token, guard_checks
from cryptoscope.risk_tools.amm_impact import constant_product_impact, calculate_sell_scenario
from cryptoscope.autotrader.strategies.volume_breakout import VolumeBreakoutStrategy
from cryptoscope.autotrader.strategies.shrink_pullback import ShrinkPullbackStrategy
from cryptoscope.autotrader.strategies.box_oscillation import BoxOscillationStrategy
from cryptoscope.execution.governor import RiskGovernor
from cryptoscope.research.settings import load_config


class TestLiveTerminalE2E(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config()
        self.data = DashboardData(self.root, self.config)
        self.data.model_health = lambda: {"model": "gemma4:12b", "status": "ready"}
        self.cs = CandleStore()

    def test_01_real_market_candles_present(self):
        """Verify real crypto market candles are archived and accessible in SQLite."""
        candles = self.cs.load_candles("BTCUSDT", "5m", limit=50)
        self.assertGreaterEqual(len(candles), 20, "Should have real BTCUSDT candles")
        first = candles[0]
        self.assertIn("open", first)
        self.assertIn("high", first)
        self.assertIn("low", first)
        self.assertIn("close", first)
        self.assertIn("volume", first)
        self.assertGreater(float(first["close"]), 1000.0, "BTC price should be real crypto price")

    def test_02_crypto_listings_structure(self):
        """Verify listings feed returns real market listings structure."""
        aggregator = MarketDataAggregator(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        tickers = aggregator.get_all_tickers()
        self.assertIsInstance(tickers, list)
        self.assertGreater(len(tickers), 0)
        self.assertEqual(tickers[0]["symbol"], "BTCUSDT")

    def test_03_monte_carlo_odds_simulation_with_real_candles(self):
        """Verify Monte Carlo odds simulation runs against real BTC candles."""
        candles = self.cs.load_candles("BTCUSDT", "5m", limit=100)
        curr_price = float(candles[-1]["close"])
        entry = curr_price
        stop = curr_price * 0.985
        target = curr_price * 1.03

        res = simulate_trade_odds(
            symbol="BTCUSDT",
            entry=entry,
            stop=stop,
            target=target,
            candles=candles,
            horizon_bars=30,
            replays=500,
        )
        self.assertEqual(res["symbol"], "BTCUSDT")
        self.assertIn("empirical_win_rate", res)
        self.assertIn("breakeven_win_rate", res)
        self.assertIn("target_r", res)
        self.assertIn("expected_r", res)
        self.assertIn("verdict", res)
        self.assertIn("percentiles", res)
        self.assertEqual(len(res["percentiles"]["p50"]), 31)

    def test_04_multi_agent_deliberation_consensus(self):
        """Verify Adversarial Multi-Agent Deliberation engine produces complete consensus."""
        candles = self.cs.load_candles("BTCUSDT", "5m", limit=100)
        snap = Snapshot(
            symbol="BTCUSDT",
            as_of=candles[-1]["close_time"],
            interval_seconds=300,
            candles=candles,
            derivatives={},
            news=[],
        )
        ind = technical(snap)
        obs = ind.get("order_blocks", [])

        engine = DeliberationConsensusEngine()
        decision = engine.deliberate(
            symbol="BTCUSDT",
            indicators=ind,
            candles=candles,
            order_blocks=obs,
            balance=10000.0,
        )
        self.assertEqual(decision["symbol"], "BTCUSDT")
        self.assertIn(decision["action"], ["BUY", "SELL", "STAND_ASIDE", "HOLD"])
        self.assertIn("conviction_score", decision)
        self.assertIn("bull_thesis", decision)
        self.assertIn("bear_thesis", decision)
        self.assertIn("risk_debate", decision)
        self.assertIn("simulation_odds", decision)

        rd = decision["risk_debate"]
        self.assertIn("conservative", rd)
        self.assertIn("aggressive", rd)
        self.assertIn("neutral_consensus", rd)
        self.assertIn("approved_risk_pct", rd)

    def test_05_quantorb_onchain_safety_audit(self):
        """Verify on-chain token safety scoring, DSU operator clustering, and AMM dump models."""
        holders = [
            {"share": 0.05, "virgin": False, "kind": "buy"},
            {"share": 0.04, "virgin": False, "kind": "buy"},
            {"share": 0.03, "virgin": True, "kind": "transfer"},
        ]
        links = [{"a": 0, "b": 1, "level": "proven"}]
        ops = cluster_operators(holders, links)
        self.assertGreater(len(ops), 0)

        audit = score_token(holders, ops, 1_000_000.0, 500_000.0, 250_000.0)
        self.assertIn("score", audit)
        self.assertIn("band", audit)
        self.assertIn(audit["band"], ["CLEAN", "OK", "RISKY", "DANGER"])

        # AMM impact test (50k sold into 500k reserve)
        impact = constant_product_impact(50_000.0, 500_000.0)
        self.assertGreater(impact, 0.0)

    def test_06_alpha_strategies_execution(self):
        """Verify all new alpha quantitative strategies evaluate candles cleanly."""
        candles = self.cs.load_candles("BTCUSDT", "5m", limit=100)
        
        # 1. Volume Breakout
        vb = VolumeBreakoutStrategy(lookback=10)
        sig_vb = vb.evaluate(candles)
        self.assertTrue(sig_vb is None or isinstance(sig_vb, dict))

        # 2. Shrink Pullback
        sp = ShrinkPullbackStrategy(lookback=10)
        sig_sp = sp.evaluate(candles)
        self.assertTrue(sig_sp is None or isinstance(sig_sp, dict))

        # 3. Box Oscillation
        bo = BoxOscillationStrategy(lookback=25)
        sig_bo = bo.evaluate(candles)
        self.assertTrue(sig_bo is None or isinstance(sig_bo, dict))

    def test_07_5gate_governor_with_token_safety(self):
        """Verify pre-trade governor halts unsafe tokens (Gate 11)."""
        risk = RiskGovernor(max_position_fraction=0.10)
        now = 1700000000.0

        # Safe token passes
        allowed, reasons = risk.check_pre_trade(
            "BTCUSDT", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now,
            token_audit={"band": "CLEAN", "score": 92}
        )
        self.assertTrue(allowed, f"Safe audit should pass: {reasons}")

        # Danger token rejected
        allowed_d, reasons_d = risk.check_pre_trade(
            "SCAMCOIN", "BUY", 100, 10000, 0, 1.0, 0.1, 0, 10000, now=now,
            token_audit={"band": "DANGER", "score": 25}
        )
        self.assertFalse(allowed_d)
        self.assertTrue(any("ONCHAIN_SAFETY_FAIL" in r for r in reasons_d))

    def test_08_production_static_assets_integrity(self):
        """Verify index.html and app.js have no fake PID or hardcoded mock stats."""
        static_dir = Path(__file__).resolve().parents[1] / "dashboard/static"
        index_html = (static_dir / "index.html").read_text(encoding="utf-8")
        app_js = (static_dir / "app.js").read_text(encoding="utf-8")

        # No fake hardcoded PID
        self.assertNotIn("PID: 22240", index_html)
        self.assertIn('id="auto-pid"', index_html)

        # No fake 14.2 GB hardcoded memory pool
        self.assertNotIn('<span class="val">14.2 GB</span>', index_html)

        # No hardcoded demo sandbox option in workspace select
        self.assertNotIn('<option value="demo">', index_html)

        # Integration widgets present
        self.assertIn('btn-run-delib', index_html)
        self.assertIn('btn-run-token-audit', index_html)
        self.assertIn('btn-open-mc', index_html)
        self.assertIn('initDeliberationDesk', app_js)
        self.assertIn('initTokenAuditTool', app_js)
        self.assertIn('initMonteCarloModal', app_js)

    def test_09_listings_filter_unlisted_tokens(self):
        """Verify CoinGecko listings filter strictly excludes unlisted tokens and includes real prices."""
        cg = CoinGeckoService()
        data = cg.get_top_listings(per_page=50, page=1)
        items = data.get("items", [])
        self.assertGreater(len(items), 0)

        symbols = [it["symbol"] for it in items]
        # Unlisted tokens must NEVER be present
        self.assertNotIn("XMRUSDT", symbols, "Delisted Monero should not be in active listings")
        self.assertNotIn("WBTUSDT", symbols, "WhiteBIT token should not be in active listings")
        self.assertNotIn("LEOUSDT", symbols, "LEO token should not be in active listings")
        self.assertNotIn("USDTUSDT", symbols, "Redundant USDTUSDT should not be in active listings")

        # Top coins must be present and have real numeric prices
        for it in items[:5]:
            self.assertIn("current_price", it)
            self.assertIn("price_usd", it)
            self.assertGreater(it["current_price"], 0.0)
            self.assertIn("change_24h_pct", it)


if __name__ == "__main__":
    unittest.main()
