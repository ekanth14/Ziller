"""BTC/ETH/SOL are excluded from autotrading; the scanner ranks everything else."""
import math

import pytest

from cryptoscope.desk.fleet import FleetManager
from cryptoscope.desk.scanner import MarketScanner
from cryptoscope.trading_universe import excluded_symbols, filter_symbols


def _ticker(sym, vol=50e6):
    return {"symbol": sym, "lastPrice": "10", "priceChangePercent": "2", "quoteVolume": str(vol),
            "highPrice": "10.5", "lowPrice": "9.5", "count": 1000}


def _uptrend(n=90, drift=0.01):
    out, p = [], 100.0
    for i in range(n):
        o = p
        p *= math.exp(drift + 0.03 * math.sin(i * 1.7))
        out.append({"open_time": i * 86400, "open": o, "high": max(o, p) * 1.01, "low": min(o, p) * 0.99,
                    "close": p, "volume": 1000.0})
    return out


def test_default_excludes_btc_eth_sol(monkeypatch):
    monkeypatch.delenv("ZILLERS_EXCLUDE_SYMBOLS", raising=False)
    assert excluded_symbols() == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    assert filter_symbols(["btcusdt", "ADAUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"]) == (["ADAUSDT", "XRPUSDT"], ["BTCUSDT", "SOLUSDT"])


def test_env_override(monkeypatch):
    monkeypatch.setenv("ZILLERS_EXCLUDE_SYMBOLS", "dogeusdt, PEPEUSDT")
    assert excluded_symbols() == {"DOGEUSDT", "PEPEUSDT"}
    monkeypatch.setenv("ZILLERS_EXCLUDE_SYMBOLS", "none")
    assert excluded_symbols() == frozenset()


def test_scanner_never_picks_excluded_and_ranks_many(monkeypatch):
    monkeypatch.delenv("ZILLERS_EXCLUDE_SYMBOLS", raising=False)
    alts = [f"ALT{i:02d}USDT" for i in range(40)]
    syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", *alts]
    tickers = [_ticker(s, vol=1e9 if s in {"BTCUSDT", "ETHUSDT", "SOLUSDT"} else 50e6) for s in syms]
    sc = MarketScanner(tickers_fetcher=lambda: tickers, live_symbols=lambda: set(syms),
                       klines_fetcher=lambda s, i, n: _uptrend(), testnet_symbols=lambda: set(syms))
    r = sc.scan("PAPER")
    reasons = {x["symbol"]: x["excluded"] for x in r["all"]}
    assert all(reasons[s] == "operator_excluded" for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    assert not {"BTCUSDT", "ETHUSDT", "SOLUSDT"} & set(r["top"])
    assert r["counts"]["scored"] == 40          # every eligible alt ranked, not just the 5 most liquid
    assert len(r["top"]) == 10                   # fleet maximum
    assert r["params"]["excluded_symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_fleet_refuses_excluded_only(tmp_path, monkeypatch):
    monkeypatch.delenv("ZILLERS_EXCLUDE_SYMBOLS", raising=False)
    with pytest.raises(ValueError, match="excluded"):
        FleetManager(tmp_path).start("PAPER", ["BTCUSDT", "ETHUSDT"], "admin")
