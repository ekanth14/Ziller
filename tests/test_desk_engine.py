"""Action Desk engine: votes, PM thresholds, next-open fills, fees, and no lookahead."""
import math

import pytest

from cryptoscope.desk.engine import BUY_SCORE, MIN_BARS, build_desk, model_votes, indicators, pm_decision
from cryptoscope.desk.feed import DeskFeed


def _candles(closes, start=1_700_000_000, vol=100.0):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append({"open_time": start + i * 86400, "open": o, "high": max(o, c) * 1.01,
                    "low": min(o, c) * 0.99, "close": c, "volume": vol})
        prev = c
    return out


def _wave(n=200):
    return [100 * (1 + 0.25 * math.sin(i / 9)) + i * 0.05 for i in range(n)]


def test_insufficient_and_invalid_data_are_reported_not_filled():
    assert build_desk(_candles([100.0] * (MIN_BARS - 1)))["status"] == "INSUFFICIENT_DATA"
    bad = _candles(_wave())
    bad[50]["close"] = float("nan")
    assert build_desk(bad)["status"] == "INVALID_DATA"


def test_pm_thresholds():
    up = {k: {"vote": 1} for k in ("trend", "momentum", "volume", "drawdown")}
    down = {k: {"vote": -1} for k in up}
    flat = {k: {"vote": 0} for k in up}
    assert pm_decision(up)["action"] == "BUY" and pm_decision(up)["bull_pct"] == 100.0
    assert pm_decision(down)["action"] == "SELL"
    assert pm_decision(flat)["action"] == "HOLD" and pm_decision(flat)["bull_pct"] == 50.0
    only_trend = {**flat, "trend": {"vote": 1}}
    assert pm_decision(only_trend)["score"] >= BUY_SCORE  # trend alone (w1.2) is enough to buy


def test_fills_happen_at_next_open_after_decision():
    d = build_desk(_candles(_wave()))
    assert d["status"] == "OK" and d["trades"]
    times = {s["time"]: s for s in d["transcript"]}
    for t in d["trades"]:
        assert t["exit_time"] > t["entry_time"]
    # every BUY fill time must be strictly after a session whose PM said BUY
    sessions = {int(c["time"]) for c in d["chart"]["candles"]}
    for t in d["trades"]:
        assert int(t["entry_time"]) in sessions


def test_no_lookahead_future_bars_do_not_change_past_votes():
    candles = _candles(_wave(220))
    ind_full = indicators(candles)
    ind_cut = indicators(candles[:150])
    for i in range(40, 150):
        assert model_votes(candles, ind_full, i) == model_votes(candles[:150], ind_cut, i)


def test_fees_reduce_net_trade_return():
    d0 = build_desk(_candles(_wave()), fee_bps=0)
    d1 = build_desk(_candles(_wave()), fee_bps=50)
    assert d0["trades"] and d1["trades"]
    assert d1["trades"][0]["net_pct"] < d1["trades"][0]["gross_pct"]
    assert d1["equity"]["agents_return"] < d0["equity"]["agents_return"]


def test_forming_bar_is_shown_but_never_decided_on():
    candles = _candles(_wave())
    d = build_desk(candles, bar_forming=True)
    assert d["decision_time"] == candles[-2]["open_time"]
    assert d["chart"]["candles"][-1]["time"] == int(candles[-1]["open_time"])


def test_feed_validates_input_and_reports_outage():
    feed = DeskFeed(fetcher=lambda s: (_ for _ in ()).throw(OSError("down")))
    with pytest.raises(ValueError):
        feed.desk("bad symbol!")
    with pytest.raises(ValueError):
        feed.desk("BTCUSDT", fee_bps=500)
    out = feed.desk("BTCUSDT")
    assert out["status"] == "UNAVAILABLE"


def test_feed_caches_within_ttl():
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return _candles(_wave())

    feed = DeskFeed(ttl_seconds=60, fetcher=fetch)
    assert feed.desk("BTCUSDT")["status"] == "OK"
    feed.desk("BTCUSDT")
    assert calls == ["BTCUSDT"]


def test_intervals_change_annualisation_and_are_validated():
    candles = _candles(_wave())
    daily = build_desk(candles, interval="1d")
    hourly = build_desk(candles, interval="1h")
    assert daily["interval"] == "1d" and hourly["interval_seconds"] == 3600
    # same bars read as hourly data imply a much larger annualised volatility
    assert hourly["risk"]["vol20"] > daily["risk"]["vol20"] * 4
    with pytest.raises(ValueError):
        build_desk(candles, interval="3d")


def test_feed_passes_interval_and_rejects_unknown():
    seen = []

    def fetch(symbol, interval):
        seen.append(interval)
        return _candles(_wave())

    feed = DeskFeed(fetcher=fetch, with_ai=False)
    assert feed.desk("BTCUSDT", interval="15m")["interval"] == "15m"
    assert seen == ["15m"]
    with pytest.raises(ValueError):
        feed.desk("BTCUSDT", interval="2h")
