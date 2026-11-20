"""Liu-Tsyvinski-Wu momentum and size ranks: shown as columns, weight 0 in the live score."""
import math

from cryptoscope.desk import scanner as sc_mod
from cryptoscope.desk.scanner import FACTOR_WEIGHTS, MarketScanner, _rank, _z


def _ticker(sym, vol):
    return {"symbol": sym, "lastPrice": "10", "priceChangePercent": "1", "quoteVolume": str(vol),
            "highPrice": "10.5", "lowPrice": "9.5", "count": 1000}


def _klines(drift, n=90):
    out, p = [], 100.0
    for i in range(n):
        o = p
        p *= math.exp(drift + 0.03 * math.sin(i * 1.7))
        out.append({"open_time": i * 86400, "open": o, "high": max(o, p) * 1.01, "low": min(o, p) * 0.99,
                    "close": p, "volume": 1000.0})
    return out


COINS = {"AAAUSDT": (0.010, 400e6), "BBBUSDT": (0.006, 90e6), "CCCUSDT": (0.002, 30e6), "DDDUSDT": (-0.004, 15e6)}


def _scan():
    tickers = [_ticker(s, v) for s, (_d, v) in COINS.items()]
    return MarketScanner(book_fetcher=None, tickers_fetcher=lambda: tickers, live_symbols=lambda: set(COINS),
                         klines_fetcher=lambda s, i, n: _klines(COINS[s][0], n)).scan("PAPER")


def test_rank_is_percentile_with_ties():
    assert _rank([3.0, 1.0, 2.0]) == [1.0, 0.0, 0.5]
    assert _rank([1.0, 1.0, 2.0]) == [0.25, 0.25, 1.0]
    assert _rank([5.0]) == [0.5]


def test_factor_ranks_are_columns_and_do_not_change_the_score():
    assert FACTOR_WEIGHTS == {"ltw_momentum": 0.0, "ltw_size": 0.0}
    r = _scan()
    by = {x["symbol"]: x for x in r["ranked"]}
    assert by["AAAUSDT"]["mom_rank"] == 1.0 and by["DDDUSDT"]["mom_rank"] == 0.0     # strongest 3-week return
    assert by["DDDUSDT"]["size_rank"] == 1.0 and by["AAAUSDT"]["size_rank"] == 0.0   # smallest coin ranks highest
    assert r["params"]["factor_weights"] == FACTOR_WEIGHTS
    scored = r["ranked"]
    zm = _z([x["factors"]["momentum"] for x in scored])
    z7 = _z([x["factors"]["r7"] for x in scored])
    zv = _z([math.log(x["quote_volume"]) for x in scored])
    za = _z([x["factors"]["atr_pct"] for x in scored])
    for x, a, b, c, d in zip(scored, zm, z7, zv, za):
        assert x["score"] == round(0.45 * a + 0.25 * b + 0.20 * c - 0.10 * d, 4)


def test_nonzero_weight_would_move_the_score(monkeypatch):
    base = {x["symbol"]: x["score"] for x in _scan()["ranked"]}
    monkeypatch.setitem(sc_mod.FACTOR_WEIGHTS, "ltw_size", 0.5)
    moved = {x["symbol"]: x["score"] for x in _scan()["ranked"]}
    assert moved["DDDUSDT"] > base["DDDUSDT"] and moved["AAAUSDT"] < base["AAAUSDT"]
