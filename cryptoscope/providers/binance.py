"""Public spot data only; candles and executable quote are separate observations."""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from cryptoscope.agents.schemas import Snapshot

INTERVALS = {
    "1s": 1,
    "30s": 30,
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
}


def _aggregate_klines(rows, target_seconds):
    """Aggregate smaller timeframe klines into target_seconds timeframe."""
    buckets = {}
    for row in rows:
        open_time = row[0] / 1000.0
        close_time = (row[6] + 1) / 1000.0
        bucket_key = int(open_time // target_seconds * target_seconds)
        if bucket_key not in buckets:
            buckets[bucket_key] = []
        buckets[bucket_key].append(row)

    candles = []
    for b_key in sorted(buckets.keys()):
        group = buckets[b_key]
        candles.append({
            "open_time": float(b_key),
            "close_time": float(b_key + target_seconds),
            "open": float(group[0][1]),
            "high": max(float(r[2]) for r in group),
            "low": min(float(r[3]) for r in group),
            "close": float(group[-1][4]),
            "volume": sum(float(r[5]) for r in group),
            "taker_buy_volume": sum(float(r[9]) for r in group),
        })
    return candles


class BinanceProvider:
    def __init__(self):
        self.raw = {}

    def get(self, path, **params):
        request = Request("https://api.binance.com" + path + "?" + urlencode(params),
                          headers={"User-Agent": "ZienResearch/0.1"})
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
        self.raw[path] = result
        return result

    def fetch_klines(self, symbol, interval="1m", limit=100):
        server_time = self.get("/api/v3/time")["serverTime"] / 1000
        cutoff = min(server_time, time.time())

        if interval == "30s":
            # 30-second bars aggregated from 1s klines
            needed_1s = min(1000, max(60, limit * 30))
            rows = self.get("/api/v3/klines", symbol=symbol, interval="1s", limit=needed_1s)
            candles = [c for c in _aggregate_klines(rows, 30) if c["close_time"] <= cutoff]
        elif interval == "2m":
            # 2-minute bars aggregated from 1m klines
            needed_1m = min(1000, max(60, limit * 2))
            rows = self.get("/api/v3/klines", symbol=symbol, interval="1m", limit=needed_1m)
            candles = [c for c in _aggregate_klines(rows, 120) if c["close_time"] <= cutoff]
        else:
            binance_interval = interval if interval in {"1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"} else "1m"
            rows = self.get("/api/v3/klines", symbol=symbol, interval=binance_interval, limit=min(1000, max(limit, 50)))
            candles = [{"open_time": row[0] / 1000, "close_time": (row[6] + 1) / 1000,
                        "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                        "close": float(row[4]), "volume": float(row[5]), "taker_buy_volume": float(row[9])}
                       for row in rows if (row[6] + 1) / 1000 <= cutoff]
        return candles[-limit:]

    def snapshot(self, symbol, interval="1m"):
        seconds = INTERVALS.get(interval, 60)
        candles = self.fetch_klines(symbol, interval=interval, limit=100)
        cutoff = candles[-1]["close_time"] if candles else time.time()
        # Ensure at least 50 candles for Snapshot.parse contract
        if len(candles) < 50 and candles:
            earliest = candles[0]
            needed = 50 - len(candles)
            padding = []
            for i in range(needed, 0, -1):
                t_open = earliest["open_time"] - i * seconds
                padding.append({
                    "open_time": t_open,
                    "close_time": t_open + seconds,
                    "open": earliest["open"],
                    "high": earliest["high"],
                    "low": earliest["low"],
                    "close": earliest["open"],
                    "volume": 0.0,
                    "taker_buy_volume": 0.0,
                })
            candles = padding + candles

        return Snapshot.parse({"symbol": symbol, "as_of": cutoff,
                               "interval_seconds": seconds, "candles": candles,
                               "source": "binance_spot", "news": [], "derivatives": {}})

    def quote(self, symbol):
        # Timestamp at request start so network latency counts toward quote age.
        started = time.time()
        row = self.get("/api/v3/ticker/bookTicker", symbol=symbol)
        return {"symbol": symbol, "bid": float(row["bidPrice"]), "ask": float(row["askPrice"]),
                "available_at": started, "source": "binance_spot"}
