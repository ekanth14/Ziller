"""Explicit offline fixture. This never represents real Laya inference."""
import time
from cryptoscope.agents.schemas import Snapshot


def demo_snapshot(now=None):
    now = time.time() if now is None else now
    end = int(now // 900) * 900
    candles = []
    for i in range(60):
        opening = 100 + i * 0.1
        start = end - (60 - i) * 900
        candles.append({"open_time": start, "close_time": start + 900, "open": opening,
                        "high": opening + 0.3, "low": opening - 0.2, "close": opening + 0.1,
                        "volume": 100, "taker_buy_volume": 60})
    return Snapshot.parse({"symbol": "BTCUSDT", "as_of": now, "interval_seconds": 900,
                           "candles": candles, "source": "synthetic_demo", "derivatives": {}, "news": []})


class DemoProvider:
    model = "DEMO_FIXTURE_NOT_LAYA"

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def complete(self, role, context):
        price = self.snapshot.candles[-1]["close"]
        if role == "trader":
            result = {"action": "LONG", "symbol": self.snapshot.symbol, "entry": price,
                      "stop": price * 0.97, "target": price * 1.08, "confidence": 0.6,
                      "thesis": "Synthetic demo fixture for pipeline verification.",
                      "evidence": ["technical"], "expires_at": self.snapshot.as_of + 1800}
        elif role == "portfolio_manager":
            result = {"approved": True, "reason": "Synthetic demo approval; apply deterministic gate."}
        elif role.endswith("risk"):
            result = {"assessment": "Demo spot position", "concerns": ["Synthetic data; fees and slippage modeled."]}
        else:
            result = {"thesis": "Synthetic trend example", "evidence": ["technical"], "counterarguments": ["Missing news and derivatives."]}
        self.calls.append({"role": role, "model": self.model, "response": result})
        return result

    def quote(self, symbol):
        price = self.snapshot.candles[-1]["close"]
        return {"symbol": symbol, "bid": price * 0.9999, "ask": price * 1.0001,
                "available_at": time.time(), "source": "synthetic_demo"}
