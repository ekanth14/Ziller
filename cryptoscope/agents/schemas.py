"""Strict, finite-number contracts at every untrusted input boundary."""
from dataclasses import asdict, dataclass
import math
import re


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    as_of: float
    interval_seconds: int
    candles: list
    derivatives: dict
    news: list
    source: str = "imported"

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError("snapshot must be an object")
        symbol = data.get("symbol", "")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{3,20}", symbol):
            raise ValueError("invalid symbol")
        as_of = number(data.get("as_of"), "as_of", 1)
        interval = number(data.get("interval_seconds"), "interval_seconds", 1)
        if interval != int(interval):
            raise ValueError("interval_seconds must be an integer")
        candles = data.get("candles", [])
        if not isinstance(candles, list) or len(candles) < 50:
            raise ValueError("at least 50 closed candles are required")
        previous = None
        normalized = []
        for candle in candles:
            row = {k: number(candle.get(k), k) for k in
                   ("open_time", "close_time", "open", "high", "low", "close", "volume", "taker_buy_volume")}
            if row["low"] <= 0 or not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                raise ValueError("invalid OHLC prices")
            if row["open_time"] >= row["close_time"] or row["close_time"] > as_of:
                raise ValueError("open or future candle refused")
            if previous is not None and abs(row["open_time"] - previous - interval) > 0.01:
                raise ValueError("candles must be ordered and contiguous")
            if abs(row["close_time"] - row["open_time"] - interval) > 0.01:
                raise ValueError("candle duration does not match interval")
            if row["taker_buy_volume"] > row["volume"]:
                raise ValueError("taker volume exceeds total volume")
            previous = row["open_time"]
            normalized.append(row)
        if as_of - normalized[-1]["close_time"] > interval:
            raise ValueError("latest closed candle is missing")
        news = data.get("news", [])
        if not isinstance(news, list):
            raise ValueError("news must be a list")
        for item in news:
            published = number(item.get("published_at"), "published_at", 1)
            available = number(item.get("available_at"), "available_at", 1)
            if published > available or available > as_of:
                raise ValueError("news was unavailable at the analysis cutoff")
            if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("headline", "source")):
                raise ValueError("news needs a headline and source")
        derivatives = data.get("derivatives", {})
        if not isinstance(derivatives, dict):
            raise ValueError("derivatives must be an object")
        if derivatives:
            observed = number(derivatives.get("available_at"), "derivatives.available_at", 1)
            if observed > as_of:
                raise ValueError("future derivatives data refused")
            for key in ("funding_rate", "open_interest"):
                if key in derivatives:
                    number(derivatives[key], key, -1 if key == "funding_rate" else 0)
        return cls(symbol, as_of, int(interval), normalized, derivatives, news, str(data.get("source", "imported")))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Proposal:
    action: str
    symbol: str
    entry: float | None
    stop: float | None
    target: float | None
    confidence: float
    thesis: str
    evidence: list
    expires_at: float
    reduce_fraction: float = 1.0

    @classmethod
    def parse(cls, data, symbol):
        if not isinstance(data, dict):
            raise ValueError("proposal must be an object")
        action = data.get("action")
        if action not in {"LONG", "SHORT", "REDUCE", "CLOSE", "HOLD", "NO_TRADE"}:
            raise ValueError("invalid proposal action")
        if data.get("symbol") != symbol:
            raise ValueError("proposal symbol differs from research symbol")
        confidence = number(data.get("confidence"), "confidence")
        fraction = number(data.get("reduce_fraction", 1), "reduce_fraction", 0.000001)
        if confidence > 1 or fraction > 1:
            raise ValueError("confidence and reduce_fraction must be <= 1")
        evidence = data.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(x, str) and x.strip() for x in evidence):
            raise ValueError("proposal must cite evidence IDs")
        thesis = data.get("thesis")
        if not isinstance(thesis, str) or not thesis.strip():
            raise ValueError("proposal needs a thesis")
        levels = {k: None if data.get(k) is None else number(data[k], k, 0.00000001)
                  for k in ("entry", "stop", "target")}
        if action in {"LONG", "SHORT"} and any(x is None for x in levels.values()):
            raise ValueError("entry, stop and target are required")
        return cls(action, symbol, **levels, confidence=confidence, thesis=thesis,
                   evidence=evidence, expires_at=number(data.get("expires_at"), "expires_at", 1),
                   reduce_fraction=fraction)

    def to_dict(self):
        return asdict(self)
