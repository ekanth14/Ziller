"""Indicators use closed candles only; no synthetic fundamentals."""
def ema(values, period):
    value = sum(values[:period]) / period
    for item in values[period:]:
        value += 2 / (period + 1) * (item - value)
    return value


def detect_order_blocks(candles):
    """Detect causal SMC Bullish and Bearish Order Blocks from closed candles."""
    if len(candles) < 5:
        return []
    blocks = []
    for i in range(1, len(candles) - 2):
        prev = candles[i - 1]
        curr = candles[i]
        following = candles[i + 2]
        # Bullish Order Block: Down-candle preceding strong upward impulse breaking high (BOS)
        if curr["close"] < curr["open"] and following["close"] > prev["high"]:
            if following["low"] > curr["high"]:  # Fair Value Gap
                blocks.append({
                    "type": "BULLISH_OB",
                    "high": curr["high"],
                    "low": curr["low"],
                    "time": curr["close_time"],
                    "volume": curr["volume"],
                })
        # Bearish Order Block: Up-candle preceding downward displacement breaking low
        if curr["close"] > curr["open"] and following["close"] < prev["low"]:
            if following["high"] < curr["low"]:  # Fair Value Gap
                blocks.append({
                    "type": "BEARISH_OB",
                    "high": curr["high"],
                    "low": curr["low"],
                    "time": curr["close_time"],
                    "volume": curr["volume"],
                })
    return blocks[-6:]


def composite_directional_score(indicators, candles, order_blocks):
    """Continuous composite score from -100 (extreme bear) to +100 (extreme bull)."""
    close = indicators["close"]
    ema20 = indicators["ema20"]
    ema50 = indicators["ema50"]
    rsi14 = indicators["rsi14"]
    cvd = indicators.get("cvd_window", 0.0)

    score = 0.0
    total_volume = sum(c.get("volume", 0.0) for c in candles) or 1.0
    cvd_ratio = cvd / total_volume
    score += max(-30.0, min(30.0, cvd_ratio * 150.0))

    if ema20 > ema50 and close >= ema20:
        score += 25.0
    elif ema20 < ema50 and close <= ema20:
        score -= 25.0
    elif close >= ema20:
        score += 10.0
    else:
        score -= 10.0

    if rsi14 >= 60:
        score += min(25.0, (rsi14 - 50) * 1.5)
    elif rsi14 <= 40:
        score -= min(25.0, (50 - rsi14) * 1.5)

    if order_blocks:
        latest_ob = order_blocks[-1]
        if latest_ob["type"] == "BULLISH_OB" and close >= latest_ob["low"]:
            score += 20.0
        elif latest_ob["type"] == "BEARISH_OB" and close <= latest_ob["high"]:
            score -= 20.0

    rounded = round(max(-100.0, min(100.0, score)), 1)
    if rounded >= 50.0:
        setup = "STRONG_BULL"
    elif rounded >= 20.0:
        setup = "MODERATE_BULL"
    elif rounded <= -50.0:
        setup = "STRONG_BEAR"
    elif rounded <= -20.0:
        setup = "MODERATE_BEAR"
    else:
        setup = "NEUTRAL"
    return {"score": rounded, "setup": setup}


def technical(snapshot):
    candles = snapshot.candles
    closes = [c["close"] for c in candles]
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(x, 0) for x in changes[:14]) / 14
    loss = sum(max(-x, 0) for x in changes[:14]) / 14
    for change in changes[14:]:
        gain = (13 * gain + max(change, 0)) / 14
        loss = (13 * loss + max(-change, 0)) / 14
    rsi = 100 - 100 / (1 + gain / loss) if loss else (100 if gain else 50)
    ranges = [max(c["high"] - c["low"], abs(c["high"] - candles[i - 1]["close"]),
                  abs(c["low"] - candles[i - 1]["close"])) if i else c["high"] - c["low"]
              for i, c in enumerate(candles)]
    atr = sum(ranges[:14]) / 14
    for value in ranges[14:]:
        atr = (13 * atr + value) / 14

    cvd_window = sum(2 * c["taker_buy_volume"] - c["volume"] for c in candles)
    ema20_val = ema(closes, 20)
    ema50_val = ema(closes, 50)
    order_blocks = detect_order_blocks(candles)
    directional = composite_directional_score(
        {"close": closes[-1], "ema20": ema20_val, "ema50": ema50_val, "rsi14": rsi, "cvd_window": cvd_window},
        candles, order_blocks
    )

    return {"id": "technical", "available_at": snapshot.as_of, "status": "available",
            "close": closes[-1], "ema20": ema20_val, "ema50": ema50_val,
            "rsi14": rsi, "atr14": atr,
            "cvd_window": cvd_window,
            "order_blocks": order_blocks,
            "directional_score": directional["score"],
            "setup": directional["setup"],
            "range_low20": min(c["low"] for c in candles[-20:]),
            "range_high20": max(c["high"] for c in candles[-20:]),
            "note": "CVD covers this candle window and venue only."}


def derivatives(snapshot):
    return {"id": "derivatives", "status": "available" if snapshot.derivatives else "unavailable",
            "data": snapshot.derivatives, "note": "No direction inferred from missing funding or OI."}


def news(snapshot):
    return {"id": "news", "status": "available" if snapshot.news else "unavailable",
            "items": snapshot.news, "note": "No news supplied does not imply neutral sentiment."}
