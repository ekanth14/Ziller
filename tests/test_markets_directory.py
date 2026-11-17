"""All-Binance markets page: grouping by coin, USD conversion across quote currencies, caching."""
from cryptoscope.desk.markets import MarketDirectory, build_markets


def _s(sym, base, quote, status="TRADING"):
    return {"symbol": sym, "baseAsset": base, "quoteAsset": quote, "status": status, "isSpotTradingAllowed": True}


def _t(sym, last, chg=1.0, qv=1000.0, count=10):
    return {"symbol": sym, "lastPrice": str(last), "priceChangePercent": str(chg), "quoteVolume": str(qv), "count": count}


SYMBOLS = [_s("BTCUSDT", "BTC", "USDT"), _s("BTCTRY", "BTC", "TRY"), _s("ETHBTC", "ETH", "BTC"),
           _s("USDTTRY", "USDT", "TRY"), _s("ABCTRY", "ABC", "TRY"), _s("OLDUSDT", "OLD", "USDT", status="BREAK")]
TICKERS = [_t("BTCUSDT", 60000, 2.0, 5e8), _t("BTCTRY", 2_400_000, 2.1, 4e9), _t("ETHBTC", 0.03, -1.0, 100),
           _t("USDTTRY", 40.0, 0.0, 4e8), _t("ABCTRY", 8.0, 5.0, 4e6), _t("OLDUSDT", 1.0)]


def test_groups_by_coin_and_converts_every_quote_to_usd():
    m = build_markets(SYMBOLS, TICKERS, {"BTC": {"name": "Bitcoin", "market_cap_rank": 1}})
    coins = {c["asset"]: c for c in m["coins"]}
    assert set(coins) == {"BTC", "ETH", "USDT", "ABC"}           # BREAK pairs are not listed
    assert m["counts"] == {"coins": 4, "pairs": 5, "quotes": 3}
    btc = coins["BTC"]
    assert btc["pair_count"] == 2 and btc["name"] == "Bitcoin" and btc["usdt_pair"] == "BTCUSDT"
    assert abs(btc["volume_usd"] - (5e8 + 4e9 / 40)) < 1       # TRY volume converted via 1/USDTTRY
    assert abs(coins["ETH"]["price_usd"] - 0.03 * 60000) < 1e-6  # priced via BTC
    assert abs(coins["ABC"]["price_usd"] - 8.0 / 40) < 1e-9      # TRY-only coin still priced in USD
    assert coins["ABC"]["usdt_pair"] is None


def test_directory_caches_and_serves_stale_on_outage():
    calls = {"t": 0}

    def tickers():
        calls["t"] += 1
        if calls["t"] > 1:
            raise OSError("down")
        return TICKERS

    d = MarketDirectory(ttl_seconds=0, info_fetcher=lambda: SYMBOLS, tickers_fetcher=tickers)
    assert d.markets()["status"] == "OK"
    stale = d.markets()
    assert stale["status"] == "STALE" and stale["counts"]["coins"] == 4
