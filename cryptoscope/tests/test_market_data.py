"""Tests for truthful multi-source market data aggregator, median calculations, and candle store."""
import tempfile
import time
import unittest
from pathlib import Path

from cryptoscope.market_data.base import NormalisedTicker
from cryptoscope.market_data.aggregator import MarketDataAggregator
from cryptoscope.market_data.candle_store import CandleStore


class MarketDataAggregatorTests(unittest.TestCase):
    def setUp(self):
        self.agg = MarketDataAggregator(symbols=["BTCUSDT", "ETHUSDT"])

    def test_empty_aggregator_reports_unavailable(self):
        t = self.agg.get_ticker("BTCUSDT")
        self.assertEqual(t["status"], "unavailable")
        self.assertIsNone(t["price"])
        self.assertEqual(t["sources_reporting"], [])

    def test_single_fresh_source_reports_single_source_status(self):
        now = time.time()
        tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70000.0, bid=69999.0, ask=70001.0, source="binance",
            received_at=now,
        )
        self.agg.record_ticker(tick)
        res = self.agg.get_ticker("BTCUSDT")
        self.assertEqual(res["status"], "single-source")
        self.assertEqual(res["price"], 70000.0)
        self.assertEqual(res["sources_reporting"], ["binance"])
        self.assertEqual(res["sources_dropped_stale"], [])

    def test_multi_source_median_within_threshold_is_verified(self):
        now = time.time()
        # Three fresh sources within 0.1% of each other
        b_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70000.0, bid=69999.0, ask=70001.0, source="binance",
            received_at=now,
        )
        cb_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70050.0, bid=70049.0, ask=70051.0, source="coinbase",
            received_at=now,
        )
        kr_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=69980.0, bid=69979.0, ask=69981.0, source="kraken",
            received_at=now,
        )
        self.agg.record_ticker(b_tick)
        self.agg.record_ticker(cb_tick)
        self.agg.record_ticker(kr_tick)

        res = self.agg.get_ticker("BTCUSDT")
        self.assertEqual(res["status"], "verified")
        # Median of 69980, 70000, 70050 is 70000.0
        self.assertEqual(res["price"], 70000.0)
        self.assertEqual(res["sources_reporting"], ["binance", "coinbase", "kraken"])
        self.assertLess(res["max_deviation_pct"], 1.0)

    def test_multi_source_deviation_over_one_percent_is_unverified(self):
        now = time.time()
        # Binance at 70000, Coinbase at 71500 (>2% difference)
        b_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70000.0, bid=69999.0, ask=70001.0, source="binance",
            received_at=now,
        )
        cb_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=71500.0, bid=71499.0, ask=71501.0, source="coinbase",
            received_at=now,
        )
        self.agg.record_ticker(b_tick)
        self.agg.record_ticker(cb_tick)

        res = self.agg.get_ticker("BTCUSDT")
        self.assertEqual(res["status"], "unverified")
        self.assertGreater(res["max_deviation_pct"], 1.0)

    def test_stale_source_dropped_before_comparison(self):
        now = time.time()
        # Binance is fresh (now), Coinbase is 8 seconds old (>5s stale)
        b_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70000.0, bid=69999.0, ask=70001.0, source="binance",
            received_at=now,
        )
        cb_stale = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=72000.0, bid=71999.0, ask=72001.0, source="coinbase",
            received_at=now - 8.0,
        )
        self.agg.record_ticker(b_tick)
        self.agg.record_ticker(cb_stale)

        res = self.agg.get_ticker("BTCUSDT")
        # Stale Coinbase should be dropped -> remaining 1 source becomes 'single-source'
        self.assertEqual(res["status"], "single-source")
        self.assertEqual(res["price"], 70000.0)
        self.assertEqual(res["sources_reporting"], ["binance"])
        self.assertIn("coinbase", res["sources_dropped_stale"])

    def test_all_stale_sources_reports_stale_status(self):
        now = time.time()
        old_tick = NormalisedTicker(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
            price=70000.0, bid=69999.0, ask=70001.0, source="binance",
            received_at=now - 12.0,
        )
        self.agg.record_ticker(old_tick)
        res = self.agg.get_ticker("BTCUSDT")
        self.assertEqual(res["status"], "stale")
        self.assertEqual(res["price"], 70000.0)
        self.assertGreater(res["age_seconds"], 10.0)


class CandleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "test_crypto_candles.db"
        self.store = CandleStore(self.db_path)

    def test_save_and_load_candles(self):
        candles = [
            {"open_time": 100.0, "close_time": 160.0, "open": 50000.0, "high": 50100.0, "low": 49900.0, "close": 50050.0, "volume": 10.0, "taker_buy_volume": 6.0},
            {"open_time": 160.0, "close_time": 220.0, "open": 50050.0, "high": 50200.0, "low": 50000.0, "close": 50150.0, "volume": 12.0, "taker_buy_volume": 8.0},
        ]
        inserted = self.store.save_candles("BTCUSDT", "1m", candles, "binance")
        self.assertEqual(inserted, 2)

        loaded = self.store.load_candles("BTCUSDT", "1m", limit=10)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["open"], 50000.0)
        self.assertEqual(loaded[1]["close"], 50150.0)


if __name__ == "__main__":
    unittest.main()
