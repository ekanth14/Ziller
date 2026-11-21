"""Strategy Lab (classic + research candidates, shared backtest) and market-structure maths. Offline."""
import math

import pytest

from cryptoscope.desk.market_structure import MarketStructure, book_metrics, readings
from cryptoscope.desk.strategy_lab import STRATEGIES, backtest, run_lab, rsi, sma


def _candles(n=400, drift=0.002, amp=0.06, seed=0):
    out, prev = [], 100.0
    for i in range(n):
        c = 100 * math.exp(drift * i) * (1 + amp * math.sin(i / 11 + seed))
        out.append({"open_time": 1_700_000_000 + i * 86400, "open": prev, "high": max(prev, c) * 1.01,
                    "low": min(prev, c) * 0.99, "close": c, "volume": 1000.0})
        prev = c
    return out


def test_every_strategy_runs_and_is_causal():
    c = _candles()
    for key, (_label, _family, fn) in STRATEGIES.items():
        full = fn(c)
        assert len(full) == len(c) and set(full) <= {0, 1}, key
        cut = fn(c[:300])
        assert full[:300] == cut, f"{key} uses future bars"


def test_lab_reports_metrics_for_all_and_buy_hold():
    r = run_lab(_candles(), "1d", 10)
    assert r["status"] == "OK" and len([x for x in r["results"] if "error" not in x]) == len(STRATEGIES)
    for x in r["results"]:
        assert {"total_return", "sharpe", "max_drawdown", "trades", "p_value", "out_of_sample_return"} <= set(x)
        assert x["max_drawdown"] <= 0
    assert "Golden cross" in r["method"]
    assert run_lab(_candles(100), "1d")["status"] == "INSUFFICIENT_DATA"
    with pytest.raises(ValueError):
        run_lab(_candles(), "3d")


def test_backtest_fills_next_open_and_charges_fees():
    c = [{"open_time": i, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1} for i in range(10)]
    c[5] = {**c[5], "open": 100.0, "close": 110.0, "high": 110.0}
    for i in range(6, 10):
        c[i] = {**c[i], "open": 110.0, "close": 110.0, "high": 110.0}
    pos = [0, 0, 0, 0, 1, 1, 1, 0, 0, 0]  # decided on bar 4 close -> filled at bar 5 open (100)
    m0 = backtest(c, pos, 0, 365)
    assert abs(m0["total_return"] - 0.10) < 1e-12 and m0["trades"] == 1
    m1 = backtest(c, pos, 10, 365)
    assert m1["total_return"] < m0["total_return"]


def test_indicator_basics():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    up = rsi([float(i) for i in range(30)], 14)
    assert up[-1] == 100.0 and up[5] is None


def test_book_metrics_and_readings():
    depth = {"bids": [["99.9", "10"], ["99.0", "50"], ["98.5", "5"]], "asks": [["100.1", "2"], ["100.8", "1"], ["101.5", "1"]]}
    b = book_metrics(depth)
    assert abs(b["mid"] - 100.0) < 1e-9 and abs(b["spread_bps"] - 20.0) < 1e-6
    assert b["imbalance_1pct"] > 0.5  # bid-heavy
    txt = readings({"funding": {"rate": 0.0008}, "open_interest": {"change_24h": 0.05}, "price_change_24h": 0.03, "book": b})
    assert any("crowded long" in t for t in txt) and any("new longs" in t for t in txt)
    assert any("bid-heavy" in t for t in txt) and any("Wide spread" in t for t in txt)


def test_snapshot_maps_1000x_perps_and_degrades_without_futures():
    def getter(url):
        if "premiumIndex?symbol=PEPEUSDT" in url:
            raise OSError("no such perp")
        if "premiumIndex" in url:
            return {"lastFundingRate": "0.0001", "markPrice": "1.01", "indexPrice": "1.0", "nextFundingTime": "0"}
        if "openInterestHist" in url:
            return [{"sumOpenInterestValue": "100", "sumOpenInterest": "1"}, {"sumOpenInterestValue": "110", "sumOpenInterest": "1"}]
        if "LongShort" in url:
            return [{"longShortRatio": "1.5", "longAccount": "0.6"}]
        if "takerlongshort" in url:
            return [{"buySellRatio": "1.1", "buyVol": "11", "sellVol": "10"}]
        if "depth" in url:
            return {"bids": [["0.99", "100"]], "asks": [["1.01", "100"]]}
        return {"priceChangePercent": "1.0"}

    d = MarketStructure(getter=getter).snapshot("PEPEUSDT")
    assert d["perp_symbol"] == "1000PEPEUSDT" and abs(d["funding"]["apr"] - 0.1095) < 1e-9
    assert abs(d["open_interest"]["change_24h"] - 0.10) < 1e-9

    def spot_only(url):
        if "fapi" in url:
            raise OSError("no futures")
        return getter(url)

    d2 = MarketStructure(getter=spot_only).snapshot("ABCUSDT")
    assert d2["perpetual"] is False and d2["book"]["available"] and "funding" not in d2
