"""Tests for Phase 4: Multi-Coin Data Ingestion, Candidate Universe, and Integrity Audit."""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from cryptoscope.research.multi_coin.candidate_universe import (
    build_candidate_universe,
    STABLECOIN_BASES,
)
from cryptoscope.research.multi_coin.data_integrity import (
    verify_symbol_integrity,
    ONE_HOUR_MS,
)


def test_candidate_universe_classification():
    fixture_info = {
        "serverTime": 1700000000000,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "filters": []
            },
            {
                "symbol": "ETHUSDT",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "filters": []
            },
            {
                "symbol": "BTCUPUSDT",
                "baseAsset": "BTCUP",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "filters": []
            },
            {
                "symbol": "FDUSDUSDT",
                "baseAsset": "FDUSD",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "filters": []
            },
            {
                "symbol": "INACTUSDT",
                "baseAsset": "INACT",
                "quoteAsset": "USDT",
                "status": "BREAK",
                "permissions": ["SPOT"],
                "filters": []
            },
            {
                "symbol": "BTCBUSD",
                "baseAsset": "BTC",
                "quoteAsset": "BUSD",
                "status": "TRADING",
                "permissions": ["SPOT"],
                "filters": []
            }
        ]
    }

    universe = build_candidate_universe(fixture_info, include_delisted=True)
    assert universe["active_trading_symbols_count"] == 3
    assert "BTCUSDT" in universe["active_trading_symbols"]
    assert "ETHUSDT" in universe["active_trading_symbols"]
    assert "FDUSDUSDT" in universe["active_trading_symbols"]
    assert "BTCUPUSDT" in universe["leveraged_excluded"]
    assert "FDUSDUSDT" in universe["stablecoins_flagged"]
    assert "INACTUSDT" in universe["inactive_or_delisted_symbols"]
    assert "LUNAUSDT" in universe["inactive_or_delisted_symbols"]


def test_data_integrity_pass(tmp_path):
    # Construct clean 100-bar hourly dataframe
    start_ts = 1700000000000
    times = [start_ts + i * ONE_HOUR_MS for i in range(100)]
    df = pd.DataFrame({
        "open_time": times,
        "open": [100.0 + i for i in range(100)],
        "high": [105.0 + i for i in range(100)],
        "low": [95.0 + i for i in range(100)],
        "close": [102.0 + i for i in range(100)],
        "volume": [10.0] * 100,
        "close_time": [t + ONE_HOUR_MS - 1 for t in times],
        "quote_volume": [1000.0] * 100,
        "trades": [50] * 100,
        "taker_buy_volume": [5.0] * 100,
        "taker_buy_quote_volume": [500.0] * 100,
    })

    file_path = tmp_path / "CLEAN_COIN.parquet"
    df.to_parquet(file_path, engine="fastparquet", index=False)

    report = verify_symbol_integrity(file_path)
    assert report["passed"] is True
    assert report["status"] == "PASS"
    assert report["total_bars"] == 100
    assert report["completeness_pct"] == 100.0
    assert report["integrity_metrics"]["duplicate_timestamps"] == 0
    assert report["integrity_metrics"]["ordering_violations"] == 0
    assert report["integrity_metrics"]["gap_events"] == 0
    assert report["integrity_metrics"]["zero_or_negative_prices"] == 0


def test_data_integrity_detects_gaps_and_anomalies(tmp_path):
    # Construct dataframe with gap, duplicate, and high < low price inversion
    start_ts = 1700000000000
    times = [
        start_ts,
        start_ts + ONE_HOUR_MS,
        start_ts + ONE_HOUR_MS,          # Duplicate
        start_ts + 4 * ONE_HOUR_MS,      # Gap of 3 hours
        start_ts + 5 * ONE_HOUR_MS,
    ]
    df = pd.DataFrame({
        "open_time": times,
        "open": [100.0, 101.0, 101.0, 104.0, 105.0],
        "high": [105.0, 106.0, 106.0, 90.0, 110.0],  # Bar 3 has high(90) < low(95)
        "low": [95.0, 96.0, 96.0, 95.0, 100.0],
        "close": [102.0, 103.0, 103.0, 100.0, 105.0],
        "volume": [10.0, 10.0, 10.0, -5.0, 10.0],     # Bar 3 has negative volume
        "close_time": [t + ONE_HOUR_MS - 1 for t in times],
        "quote_volume": [1000.0] * 5,
        "trades": [50] * 5,
        "taker_buy_volume": [5.0] * 5,
        "taker_buy_quote_volume": [500.0] * 5,
    })

    file_path = tmp_path / "DIRTY_COIN.parquet"
    df.to_parquet(file_path, engine="fastparquet", index=False)

    report = verify_symbol_integrity(file_path)
    assert report["passed"] is False
    assert report["status"] == "FLAGGED"
    metrics = report["integrity_metrics"]
    assert metrics["duplicate_timestamps"] == 1
    assert metrics["gap_events"] == 1
    assert metrics["high_less_than_low"] == 1
    assert metrics["negative_volume_bars"] == 1
