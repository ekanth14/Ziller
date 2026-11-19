"""Strategy Lab: classic long-only spot strategies, backtested identically on real exchange candles.

Every strategy maps closed candles to a target position (1 = long, 0 = cash) decided on bar t's
close and executed at bar t+1's open, paying `fee_bps` per side. No parameter is fitted to the
data, so the second (out-of-sample) part of the history is an honest stability check.

Strategies and formulas
  EMA cross        long while EMA(12) > EMA(26)
  MACD + trend     long while MACD(12,26) > signal(9) and close > EMA(100)
  Donchian (Turtle) enter close > highest high(20) of the previous bars; exit close < lowest low(10)
  Bollinger revert enter close < SMA20 - 2*sd20; exit close >= SMA20
  RSI-2 (Connors)  enter RSI(2) < 10 and close > SMA(100); exit RSI(2) > 70 or close > SMA(5)
  Supertrend       ATR(10), multiplier 3: long while price is above the trailing band
  Keltner break    enter close > EMA20 + 2*ATR(20); exit close < EMA20
  Ichimoku         long while close > cloud (max(Senkou A, Senkou B), displaced 26) and Tenkan(9) > Kijun(26)
  TS momentum      long while 30-bar rate of change > 0 and close > SMA(50)
  Vol breakout     (Williams) enter close > open + 0.5 * previous range; exit after 3 bars or close < SMA(10)
  Heikin-Ashi      long after 2 consecutive bullish HA candles; exit on the first bearish HA candle
  Parabolic SAR    (0.02 / 0.2) long while SAR is below price
  Golden cross     long while SMA(50) > SMA(200)

Metrics: total return, CAGR, annualised volatility, Sharpe, Sortino, max drawdown, Calmar,
trades, win rate, profit factor, average trade, exposure, buy-and-hold comparison, in-sample vs
out-of-sample return, and a permutation p-value (strategy timing vs the same exposure placed at
random, 1,000 shuffles).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence

from cryptoscope.desk.engine import INTERVALS, YEAR_SECONDS, significance

Candles = Sequence[Dict[str, float]]


# --------------------------------------------------------------------------- indicators
def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    k, out = 2 / (n + 1), []
    for i, v in enumerate(x):
        out.append(v if i == 0 else k * v + (1 - k) * out[-1])
    return out


def stdev(x, n):
    out = [None] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        m = sum(w) / n
        out[i] = math.sqrt(sum((v - m) ** 2 for v in w) / n)
    return out


def rsi(x, n):
    out, ag, al = [None] * len(x), 0.0, 0.0
    for i in range(1, len(x)):
        d = x[i] - x[i - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            ag += g / n
            al += l / n
            if i == n:
                out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        else:
            ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(c: Candles, n):
    tr = [c[0]["high"] - c[0]["low"]] + [max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]),
                                              abs(c[i]["low"] - c[i - 1]["close"])) for i in range(1, len(c))]
    out, a = [None] * len(c), None
    for i, v in enumerate(tr):  # Wilder smoothing
        if i == n - 1:
            a = sum(tr[:n]) / n
        elif i >= n:
            a = (a * (n - 1) + v) / n
        out[i] = a
    return out


def _hold(enter: Callable[[int], bool], exit_: Callable[[int], bool], n: int, start: int) -> List[int]:
    pos, cur = [0] * n, 0
    for i in range(start, n):
        if cur == 0 and enter(i):
            cur = 1
        elif cur == 1 and exit_(i):
            cur = 0
        pos[i] = cur
    return pos


# --------------------------------------------------------------------------- strategies
def s_ema_cross(c):
    cl = [b["close"] for b in c]
    f, s = ema(cl, 12), ema(cl, 26)
    return [1 if i >= 26 and f[i] > s[i] else 0 for i in range(len(c))]


def s_macd_trend(c):
    cl = [b["close"] for b in c]
    macd = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
    sig, trend = ema(macd, 9), ema(cl, 100)
    return [1 if i >= 100 and macd[i] > sig[i] and cl[i] > trend[i] else 0 for i in range(len(c))]


def s_donchian(c):
    hi, lo, cl = [b["high"] for b in c], [b["low"] for b in c], [b["close"] for b in c]
    return _hold(lambda i: cl[i] > max(hi[i - 20:i]), lambda i: cl[i] < min(lo[i - 10:i]), len(c), 20)


def s_bollinger(c):
    cl = [b["close"] for b in c]
    m, sd = sma(cl, 20), stdev(cl, 20)
    return _hold(lambda i: cl[i] < m[i] - 2 * sd[i], lambda i: cl[i] >= m[i], len(c), 20)


def s_rsi2(c):
    cl = [b["close"] for b in c]
    r, s100, s5 = rsi(cl, 2), sma(cl, 100), sma(cl, 5)
    return _hold(lambda i: r[i] is not None and r[i] < 10 and cl[i] > s100[i],
                 lambda i: (r[i] or 0) > 70 or cl[i] > s5[i], len(c), 100)


def s_supertrend(c, n=10, mult=3.0):
    a = atr(c, n)
    pos, up, dn, trend = [0] * len(c), None, None, 1
    for i in range(n, len(c)):
        mid = (c[i]["high"] + c[i]["low"]) / 2
        bu, bd = mid - mult * a[i], mid + mult * a[i]
        prev_close = c[i - 1]["close"]
        up = bu if up is None or prev_close < up else max(bu, up)
        dn = bd if dn is None or prev_close > dn else min(bd, dn)
        if c[i]["close"] > dn:
            trend = 1
        elif c[i]["close"] < up:
            trend = -1
        pos[i] = 1 if trend == 1 else 0
    return pos


def s_keltner(c):
    cl = [b["close"] for b in c]
    e, a = ema(cl, 20), atr(c, 20)
    return _hold(lambda i: cl[i] > e[i] + 2 * a[i], lambda i: cl[i] < e[i], len(c), 20)


def s_ichimoku(c):
    hi, lo, cl = [b["high"] for b in c], [b["low"] for b in c], [b["close"] for b in c]
    mid = lambda i, n: (max(hi[i - n + 1:i + 1]) + min(lo[i - n + 1:i + 1])) / 2  # noqa: E731
    pos = [0] * len(c)
    for i in range(52 + 26, len(c)):
        tenkan, kijun = mid(i, 9), mid(i, 26)
        j = i - 26  # the cloud plotted at i was computed 26 bars earlier
        span_a = (mid(j, 9) + mid(j, 26)) / 2
        span_b = mid(j, 52)
        pos[i] = 1 if cl[i] > max(span_a, span_b) and tenkan > kijun else 0
    return pos


def s_ts_momentum(c):
    cl = [b["close"] for b in c]
    s50 = sma(cl, 50)
    return [1 if i >= 50 and cl[i] / cl[i - 30] - 1 > 0 and cl[i] > s50[i] else 0 for i in range(len(c))]


def s_vol_breakout(c, k=0.5, hold=3):
    cl = [b["close"] for b in c]
    s10 = sma(cl, 10)
    pos, cur, held = [0] * len(c), 0, 0
    for i in range(10, len(c)):
        prev_range = c[i - 1]["high"] - c[i - 1]["low"]
        if cur == 0 and cl[i] > c[i]["open"] + k * prev_range:
            cur, held = 1, 0
        elif cur == 1:
            held += 1
            if held >= hold or cl[i] < s10[i]:
                cur = 0
        pos[i] = cur
    return pos


def s_heikin_ashi(c):
    ha_o, ha_c, pos, cur, streak = [], [], [0] * len(c), 0, 0
    for i, b in enumerate(c):
        hc = (b["open"] + b["high"] + b["low"] + b["close"]) / 4
        ho = (b["open"] + b["close"]) / 2 if i == 0 else (ha_o[-1] + ha_c[-1]) / 2
        ha_o.append(ho)
        ha_c.append(hc)
        bull = hc > ho
        streak = streak + 1 if bull else 0
        if cur == 0 and streak >= 2:
            cur = 1
        elif cur == 1 and not bull:
            cur = 0
        pos[i] = cur
    return pos


def s_psar(c, step=0.02, max_af=0.2):
    if len(c) < 3:
        return [0] * len(c)
    pos, up = [0] * len(c), True
    sar, ep, af = c[0]["low"], c[0]["high"], step
    for i in range(1, len(c)):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, c[i - 1]["low"], c[i - 2]["low"] if i > 1 else c[i - 1]["low"])
            if c[i]["low"] < sar:
                up, sar, ep, af = False, ep, c[i]["low"], step
            elif c[i]["high"] > ep:
                ep, af = c[i]["high"], min(max_af, af + step)
        else:
            sar = max(sar, c[i - 1]["high"], c[i - 2]["high"] if i > 1 else c[i - 1]["high"])
            if c[i]["high"] > sar:
                up, sar, ep, af = True, ep, c[i]["high"], step
            elif c[i]["low"] < ep:
                ep, af = c[i]["low"], min(max_af, af + step)
        pos[i] = 1 if up else 0
    return pos


def s_golden_cross(c):
    cl = [b["close"] for b in c]
    f, s = sma(cl, 50), sma(cl, 200)
    return [1 if i >= 200 and f[i] > s[i] else 0 for i in range(len(c))]


STRATEGIES: Dict[str, tuple] = {
    "ema_cross": ("EMA cross 12/26", "trend", s_ema_cross),
    "macd_trend": ("MACD + EMA100 filter", "trend", s_macd_trend),
    "donchian": ("Donchian / Turtle 20-10", "breakout", s_donchian),
    "bollinger": ("Bollinger mean reversion", "mean reversion", s_bollinger),
    "rsi2": ("RSI-2 (Connors)", "mean reversion", s_rsi2),
    "supertrend": ("Supertrend 10x3", "trend", s_supertrend),
    "keltner": ("Keltner breakout", "breakout", s_keltner),
    "ichimoku": ("Ichimoku cloud", "trend", s_ichimoku),
    "ts_momentum": ("Time-series momentum 30", "momentum", s_ts_momentum),
    "vol_breakout": ("Williams volatility breakout", "breakout", s_vol_breakout),
    "heikin_ashi": ("Heikin-Ashi trend", "trend", s_heikin_ashi),
    "psar": ("Parabolic SAR", "trend", s_psar),
    "golden_cross": ("Golden cross SMA 50/200", "trend", s_golden_cross),
}


# --------------------------------------------------------------------------- backtest
def backtest(c: Candles, pos: Sequence[int], fee_bps: float, bars_per_year: float, oos_split: float = 0.7) -> Dict[str, object]:
    """Position decided on bar t close, executed at bar t+1 open."""
    n, fee = len(c), fee_bps / 10000
    eq, curve, rets = 1.0, [1.0], []
    trades, cur, entry, held_bars = [], 0, None, 0
    for t in range(1, n):
        want = pos[t - 1]
        o, cl, prev = c[t]["open"], c[t]["close"], c[t - 1]["close"]
        r = 0.0
        if want == 1 and cur == 0:
            r = (cl / o) * (1 - fee) - 1
            cur, entry = 1, o
        elif want == 0 and cur == 1:
            r = (o / prev) * (1 - fee) - 1
            trades.append((o / entry) * (1 - fee) ** 2 - 1)
            cur, entry = 0, None
        elif cur == 1:
            r = cl / prev - 1
        held_bars += cur
        eq *= 1 + r
        curve.append(eq)
        rets.append(r)
    if cur == 1:  # mark open trade at last close
        trades.append((c[-1]["close"] / entry) * (1 - fee) - 1)
    peak, mdd = 1.0, 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
    down = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in down) / len(rets)) if rets and down else 0.0
    years = len(rets) / bars_per_year if bars_per_year else 0
    cagr = curve[-1] ** (1 / years) - 1 if years > 0 and curve[-1] > 0 else None
    wins, losses = [x for x in trades if x > 0], [x for x in trades if x <= 0]
    split = max(1, int(n * oos_split))
    fwd = [c[t + 1]["close"] / c[t]["close"] - 1 for t in range(n - 1)]
    p = significance([1 if x else -1 for x in pos[:-1]], fwd) if any(pos) and not all(pos) else None
    return {
        "total_return": curve[-1] - 1, "cagr": cagr,
        "vol": sd * math.sqrt(bars_per_year), "sharpe": mean / sd * math.sqrt(bars_per_year) if sd else 0.0,
        "sortino": mean / dsd * math.sqrt(bars_per_year) if dsd else None,
        "max_drawdown": mdd, "calmar": (cagr / -mdd) if cagr is not None and mdd < 0 else None,
        "trades": len(trades), "win_rate": len(wins) / len(trades) if trades else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None,
        "avg_trade": sum(trades) / len(trades) if trades else None,
        "exposure": held_bars / max(1, n - 1),
        "in_sample_return": curve[split - 1] - 1, "out_of_sample_return": curve[-1] / curve[split - 1] - 1,
        "p_value": p, "curve": curve,
    }


def run_lab(c: Candles, interval: str = "1d", fee_bps: float = 10.0, only: Optional[List[str]] = None) -> Dict[str, object]:
    if interval not in INTERVALS:
        raise ValueError("Unsupported interval")
    if len(c) < 150:
        return {"status": "INSUFFICIENT_DATA", "bars": len(c), "required": 150}
    bpy = YEAR_SECONDS / INTERVALS[interval]
    bh_curve = [b["close"] / c[0]["open"] for b in c]
    bh = {"total_return": c[-1]["close"] / c[0]["open"] - 1,
          "max_drawdown": min(v / max(bh_curve[:i + 1]) - 1 for i, v in enumerate(bh_curve))}
    rows = []
    for key, (label, family, fn) in STRATEGIES.items():
        if only and key not in only:
            continue
        try:
            m = backtest(c, fn(c), fee_bps, bpy)
        except Exception as exc:  # one broken strategy never takes the lab down
            rows.append({"key": key, "label": label, "family": family, "error": type(exc).__name__})
            continue
        m["beats_hold"] = m["total_return"] > bh["total_return"]
        rows.append({"key": key, "label": label, "family": family, **m})
    ok = [r for r in rows if "error" not in r]
    m_tests = max(1, len(ok))
    for r in ok:  # Bonferroni across all strategies tested on the same data
        r["significant"] = r["p_value"] is not None and r["p_value"] < 0.05 / m_tests
    ok.sort(key=lambda r: -r["sharpe"])
    step = max(1, len(c) // 300)
    return {"status": "OK", "interval": interval, "bars": len(c), "fee_bps": fee_bps,
            "from": c[0]["open_time"], "to": c[-1]["open_time"], "buy_hold": bh,
            "times": [int(b["open_time"]) for b in c[::step]],
            "buy_hold_curve": bh_curve[::step],
            "results": [{**r, "curve": r["curve"][::step]} for r in ok] + [r for r in rows if "error" in r],
            "method": __doc__.split("Strategies and formulas", 1)[1].strip()}
