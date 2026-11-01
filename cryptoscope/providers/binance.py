"""Public spot data only; candles and executable quote are separate observations."""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from cryptoscope.agents.schemas import Snapshot

INTERVALS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


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

    def snapshot(self, symbol, interval):
        seconds = INTERVALS[interval]
        server_time = self.get("/api/v3/time")["serverTime"] / 1000
        rows = self.get("/api/v3/klines", symbol=symbol, interval=interval, limit=201)
        # An exchange clock slightly ahead of this host must not turn a
        # closed-bar snapshot into future evidence on the receiving machine.
        cutoff = min(server_time, time.time())
        candles = [{"open_time": row[0] / 1000, "close_time": (row[6] + 1) / 1000,
                    "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                    "close": float(row[4]), "volume": float(row[5]), "taker_buy_volume": float(row[9])}
                   for row in rows if (row[6] + 1) / 1000 <= cutoff]
        return Snapshot.parse({"symbol": symbol, "as_of": cutoff,
                               "interval_seconds": seconds, "candles": candles,
                               "source": "binance_spot", "news": [], "derivatives": {}})

    def quote(self, symbol):
        # Timestamp at request start so network latency counts toward quote age.
        started = time.time()
        row = self.get("/api/v3/ticker/bookTicker", symbol=symbol)
        return {"symbol": symbol, "bid": float(row["bidPrice"]), "ask": float(row["askPrice"]),
                "available_at": started, "source": "binance_spot"}
