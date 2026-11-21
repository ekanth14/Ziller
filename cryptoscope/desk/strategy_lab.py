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
Candidates added from the research review (all long-only, same backtest):
  Vol-scaled TSMOM enter when 30-bar log return / (sd of 1-bar log returns(30) * sqrt(30)) > 1; exit < 0
  Keltner squeeze  squeeze = Bollinger(20, 2sd) inside Keltner(EMA20 +/- 1.5*ATR20); enter on the first bar
                   out of a squeeze with close > SMA20 and rising; exit close < EMA20
  VWAP reversion   VWAP20 = sum(typical price * volume) / sum(volume) over 20 bars; enter when
                   close - VWAP20 < -2 sd(close - VWAP20, 20); exit close >= VWAP20
  ADX trend        long while ADX(14) > 25 and +DI > -DI
  Aroon trend      long while Aroon up(14) > 70 and up > down
  Stoch-RSI cross  enter %K crosses above %D below 20; exit %K > 80
  CCI reversion    enter CCI(14) crosses back above -100; exit CCI > 0
  MFI reversion    enter MFI(14) < 20; exit MFI > 50
  Hull MA trend    long while close > HMA(55) and HMA rising
  KAMA trend       long while close > KAMA(10, 2, 30) and KAMA rising
  Vortex           long while VI+(14) > VI-(14)
  (Donchian, Bollinger, Keltner, Supertrend, Ichimoku and TS momentum above are gate candidates too.)

Promotion gate (per candidate, same candles):
  every entry (position 0 -> 1) becomes a bracket trade from StrategyBot.bracket("SCALP", ATR14%):
  target / stop / 4 h time limit, fee max(fee, 10 bp) per side, labelled with the triple barrier.
  OOS trades  trades whose signal and exit sit inside one CPCV group (10 groups)
  DSR p       1 - Deflated Sharpe of per-trade returns, trials = candidates tested
  PBO         CSCV over all candidates (C(10,5) splits, purged + embargoed)
  PASS        OOS trades >= 100, DSR p < 0.05, PBO < 0.3 and expectancy after fees > 0

Metrics: total return, CAGR, annualised volatility, Sharpe, Sortino, max drawdown, Calmar,
trades, win rate, profit factor, average trade, exposure, buy-and-hold comparison, in-sample vs
out-of-sample return, and a permutation p-value (strategy timing vs the same exposure placed at
random, 1,000 shuffles).
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from core.quant.validation import (deflated_sharpe, group_bounds, probability_of_backtest_overfitting,
                                   triple_barrier_labels)
from cryptoscope.desk.engine import INTERVALS, YEAR_SECONDS, significance
from cryptoscope.orchestrator.bots.strategy_bot import bracket

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


# --------------------------------------------------------------------------- research candidates
def s_vol_tsmom(c, look=30, vol_n=30, enter_z=1.0):
    """Time-series momentum scaled by volatility: the lookback return in units of its own noise."""
    cl = [b["close"] for b in c]
    lr = [0.0] + [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
    sd = stdev(lr, vol_n)

    def z(i):
        return math.log(cl[i] / cl[i - look]) / (sd[i] * math.sqrt(look)) if sd[i] else 0.0
    return _hold(lambda i: z(i) > enter_z, lambda i: z(i) < 0, len(c), max(look, vol_n) + 1)


def s_keltner_squeeze(c):
    cl = [b["close"] for b in c]
    m, sd, e, a = sma(cl, 20), stdev(cl, 20), ema(cl, 20), atr(c, 20)

    def squeeze(i):
        return m[i] + 2 * sd[i] < e[i] + 1.5 * a[i] and m[i] - 2 * sd[i] > e[i] - 1.5 * a[i]
    return _hold(lambda i: squeeze(i - 1) and not squeeze(i) and cl[i] > m[i] and cl[i] > cl[i - 1],
                 lambda i: cl[i] < e[i], len(c), 21)


def s_vwap_revert(c, n=20, k=2.0):
    cl = [b["close"] for b in c]
    pv = [(b["high"] + b["low"] + b["close"]) / 3 * b["volume"] for b in c]
    vol = [b["volume"] for b in c]
    vw = [None] * len(c)
    for i in range(n - 1, len(c)):
        v = sum(vol[i - n + 1:i + 1])
        vw[i] = sum(pv[i - n + 1:i + 1]) / v if v > 0 else cl[i]
    dev = [cl[i] - vw[i] if vw[i] is not None else 0.0 for i in range(len(c))]
    sd = stdev(dev, n)
    return _hold(lambda i: bool(sd[i]) and dev[i] < -k * sd[i], lambda i: cl[i] >= vw[i], len(c), 2 * n)


def _ta(c, name, **kw):
    """One pandas-ta-classic indicator (from the catalog) as row tuples; NaN becomes None."""
    from cryptoscope.desk.indicator_catalog import candles_frame
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = getattr(candles_frame(c).ta, name)(**kw)
    if not hasattr(out, "columns"):
        out = out.to_frame()
    return [tuple(None if v != v else float(v) for v in row) for row in out.itertuples(index=False)]


def _ok(*vals):
    return all(v is not None for v in vals)


def s_adx_trend(c):
    x = _ta(c, "adx", length=14)  # ADX, +DI, -DI
    return [1 if _ok(*x[i]) and x[i][0] > 25 and x[i][1] > x[i][2] else 0 for i in range(len(c))]


def s_aroon(c):
    x = _ta(c, "aroon", length=14)  # down, up, oscillator
    return [1 if _ok(*x[i]) and x[i][1] > 70 and x[i][1] > x[i][0] else 0 for i in range(len(c))]


def s_stochrsi(c):
    x = _ta(c, "stochrsi")  # %K, %D
    return _hold(lambda i: _ok(*x[i], *x[i - 1]) and x[i - 1][0] <= x[i - 1][1] and x[i][0] > x[i][1] and x[i][0] < 20,
                 lambda i: _ok(x[i][0]) and x[i][0] > 80, len(c), 1)


def s_cci_revert(c):
    x = [r[0] for r in _ta(c, "cci", length=14)]
    return _hold(lambda i: _ok(x[i], x[i - 1]) and x[i - 1] < -100 <= x[i], lambda i: _ok(x[i]) and x[i] > 0, len(c), 1)


def s_mfi_revert(c):
    x = [r[0] for r in _ta(c, "mfi", length=14)]
    return _hold(lambda i: _ok(x[i]) and x[i] < 20, lambda i: _ok(x[i]) and x[i] > 50, len(c), 1)


def _above_rising(c, ma):
    cl = [b["close"] for b in c]
    return [1 if i > 0 and _ok(ma[i], ma[i - 1]) and cl[i] > ma[i] > ma[i - 1] else 0 for i in range(len(c))]


def s_hma_trend(c):
    return _above_rising(c, [r[0] for r in _ta(c, "hma", length=55)])


def s_kama_trend(c):
    return _above_rising(c, [r[0] for r in _ta(c, "kama", length=10, fast=2, slow=30)])


def s_vortex(c):
    x = _ta(c, "vortex", length=14)  # VI+, VI-
    return [1 if _ok(*x[i]) and x[i][0] > x[i][1] else 0 for i in range(len(c))]


# --------------------------------------------------------------------------- research additions (2026-11-21)
# From the deep-research report: exits that let winners run (Kaminski & Lo: stops only help when returns
# trend, so they are wide and volatility-scaled) and well-defined rules not yet tested on crypto. Every
# one is only a CANDIDATE: the gate (OOS trades, DSR, PBO, expectancy after fees) decides.

def _entries_with_trailing_exit(c, entry: Callable[[int], bool], start: int, n_atr: int = 22, mult: float = 3.0,
                                chandelier: bool = True, max_hold: Optional[int] = None) -> List[int]:
    """Enter on `entry`; exit ONLY when the close breaks a ratcheting trailing stop.

    Chandelier (LeBeau): stop = highest high since entry - mult * ATR(n). ATR trail: highest close since
    entry - mult * ATR(n). The stop never moves down. Optional time stop after `max_hold` bars."""
    hi, cl = [b["high"] for b in c], [b["close"] for b in c]
    a = atr(c, n_atr)
    pos, cur, stop, peak, held = [0] * len(c), 0, None, None, 0
    for i in range(max(start, n_atr + 1), len(c)):
        if cur == 0:
            if entry(i) and a[i]:
                cur, peak, held = 1, (hi[i] if chandelier else cl[i]), 0
                stop = peak - mult * a[i]
        else:
            held += 1
            peak = max(peak, hi[i] if chandelier else cl[i])
            if a[i]:
                stop = max(stop, peak - mult * a[i])
            if cl[i] < stop or (max_hold and held >= max_hold):
                cur = 0
        pos[i] = cur
    return pos


def s_donchian_chandelier(c):
    hi, cl = [b["high"] for b in c], [b["close"] for b in c]
    return _entries_with_trailing_exit(c, lambda i: cl[i] > max(hi[i - 20:i]), 20)


def s_tsmom_chandelier(c):
    cl = [b["close"] for b in c]
    s50 = sma(cl, 50)
    return _entries_with_trailing_exit(c, lambda i: i >= 50 and cl[i] / cl[i - 30] > 1 and s50[i] is not None and cl[i] > s50[i], 50)


def s_ema_atr_trail(c):
    cl = [b["close"] for b in c]
    f, s = ema(cl, 12), ema(cl, 26)
    return _entries_with_trailing_exit(c, lambda i: f[i] > s[i] and f[i - 1] <= s[i - 1], 27, n_atr=14, mult=2.5,
                                       chandelier=False)


def s_nr7(c, hold: int = 5):
    """Crabel NR7: the narrowest range of the last 7 bars; go long when a later close breaks its high
    (within 3 bars); exit after `hold` bars or on a close below the NR7 low."""
    hi, lo, cl = [b["high"] for b in c], [b["low"] for b in c], [b["close"] for b in c]
    rng = [h - l for h, l in zip(hi, lo)]
    pos, cur, held, setup = [0] * len(c), 0, 0, None
    for i in range(7, len(c)):
        if cur == 0:
            if setup and i - setup[0] <= 3 and cl[i] > setup[1]:
                cur, held, floor = 1, 0, setup[2]
            elif rng[i - 1] == min(rng[i - 7:i]):
                setup = (i - 1, hi[i - 1], lo[i - 1])
        else:
            held += 1
            if held >= hold or cl[i] < floor:
                cur, setup = 0, None
        pos[i] = cur
    return pos


def s_inside_bar(c, hold: int = 5):
    """Inside bar (high < prior high and low > prior low), long on a close above the mother bar's high;
    exit on a close below the mother bar's low or after `hold` bars."""
    hi, lo, cl = [b["high"] for b in c], [b["low"] for b in c], [b["close"] for b in c]
    pos, cur, held, mother = [0] * len(c), 0, 0, None
    for i in range(2, len(c)):
        if cur == 0:
            if hi[i - 1] < hi[i - 2] and lo[i - 1] > lo[i - 2]:
                mother = (hi[i - 2], lo[i - 2])
            if mother and cl[i] > mother[0]:
                cur, held, floor = 1, 0, mother[1]
        else:
            held += 1
            if held >= hold or cl[i] < floor:
                cur, mother = 0, None
        pos[i] = cur
    return pos


def _percent_rank(xs, i, n):
    """Share of the previous n values strictly below xs[i] (0-100)."""
    window = xs[max(0, i - n):i]
    return 100.0 * sum(1 for v in window if v < xs[i]) / len(window) if window else None


def connors_rsi(c, n_rsi: int = 3, n_streak: int = 2, n_rank: int = 100) -> List[Optional[float]]:
    """Connors RSI = mean(RSI(close, 3), RSI(up/down streak, 2), PercentRank(1-bar return, 100))."""
    cl = [b["close"] for b in c]
    streak = [0.0]
    for i in range(1, len(cl)):
        s = streak[-1]
        streak.append((s + 1 if s >= 0 else 1) if cl[i] > cl[i - 1] else (s - 1 if s <= 0 else -1) if cl[i] < cl[i - 1] else 0)
    r1, r2 = rsi(cl, n_rsi), rsi(streak, n_streak)
    roc = [None] + [cl[i] / cl[i - 1] - 1 for i in range(1, len(cl))]
    out: List[Optional[float]] = [None] * len(cl)
    for i in range(n_rank + 1, len(cl)):
        pr = _percent_rank(roc, i, n_rank)
        if r1[i] is not None and r2[i] is not None and pr is not None:
            out[i] = (r1[i] + r2[i] + pr) / 3
    return out


def s_connors_rsi(c):
    """Long when Connors RSI < 10 above the 200-bar SMA; exit when CRSI > 70."""
    cl = [b["close"] for b in c]
    cr, s200 = connors_rsi(c), sma(cl, 200)
    return _hold(lambda i: cr[i] is not None and s200[i] is not None and cr[i] < 10 and cl[i] > s200[i],
                 lambda i: cr[i] is not None and cr[i] > 70, len(c), 201)


def s_zscore_revert(c, n: int = 20):
    """Long when the close is 2 sd below its n-bar mean in an uptrend (above SMA100); exit at the mean."""
    cl = [b["close"] for b in c]
    m, sd, s100 = sma(cl, n), stdev(cl, n), sma(cl, 100)
    z = lambda i: (cl[i] - m[i]) / sd[i] if m[i] is not None and sd[i] else None  # noqa: E731
    return _hold(lambda i: z(i) is not None and s100[i] is not None and z(i) < -2 and cl[i] > s100[i],
                 lambda i: z(i) is not None and z(i) >= 0, len(c), 100)


def s_turn_of_month(c):
    """Hold from the last day of each month through the 3rd day of the next (UTC). Daily bars only."""
    import datetime as _dt
    out = []
    for b in c:
        d = _dt.datetime.fromtimestamp(b["open_time"], _dt.timezone.utc)
        last = (d + _dt.timedelta(days=1)).month != d.month
        out.append(1 if last or d.day <= 3 else 0)
    span = (c[-1]["open_time"] - c[0]["open_time"]) / max(1, len(c) - 1) if len(c) > 1 else 0
    return out if 80_000 <= span <= 90_000 else [0] * len(c)     # not meaningful on intraday bars


def s_utc_orb(c, first_hours: float = 1.0):
    """Opening-range breakout adapted to 24/7 markets: range = first `first_hours` of the UTC day; long on a
    close above the range high; flat at the end of the UTC day or on a close below the range low.
    Intraday bars (15m-1h) only."""
    span = (c[-1]["open_time"] - c[0]["open_time"]) / max(1, len(c) - 1) if len(c) > 1 else 0
    if not 60 <= span <= 3600:
        return [0] * len(c)
    pos, cur, day, rh, rl = [0] * len(c), 0, None, None, None
    for i, b in enumerate(c):
        d, sec = int(b["open_time"] // 86400), b["open_time"] % 86400
        if d != day:
            day, rh, rl, cur = d, b["high"], b["low"], 0
        elif sec < first_hours * 3600:
            rh, rl = max(rh, b["high"]), min(rl, b["low"])
        elif cur == 0 and b["close"] > rh:
            cur = 1
        elif cur == 1 and b["close"] < rl:
            cur = 0
        if sec + span >= 86400:   # last bar of the UTC day: flat
            cur = 0
        pos[i] = cur
    return pos


def _library(cls_name: str, window: int = 120, max_hold: int = 10):
    """Wrap a desk strategy-library rule (cryptoscope/autotrader/strategies) as a Lab position series.

    Replays the rule bar by bar on a trailing window of closed bars only (no lookahead): long on its
    BUY, flat on its SELL or after `max_hold` bars, so it faces the same gate as every other candidate.
    """
    def run(c):
        import cryptoscope.autotrader.strategies as lib
        from cryptoscope.desk.ai_layer import _strategy_indicators
        strat = getattr(lib, cls_name)()
        n, pos, cur, held = len(c), [0] * len(c), 0, 0
        for i in range(60, n):
            rows = [dict(x, close_time=x.get("close_time", x.get("open_time", i))) for x in c[max(0, i - window + 1):i + 1]]
            try:
                side = (strat.evaluate(rows, _strategy_indicators(rows)) or {}).get("side")
            except Exception:
                side = None
            if cur == 0 and side == "BUY":
                cur, held = 1, 0
            elif cur == 1:
                held += 1
                if side == "SELL" or held >= max_hold:
                    cur = 0
            pos[i] = cur
        return pos
    return run


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
    # research candidates: volatility-scaled momentum, squeeze, VWAP and pandas-ta-classic catalog rules
    "vol_tsmom": ("Vol-scaled TS momentum 30", "momentum", s_vol_tsmom),
    "keltner_squeeze": ("Keltner squeeze breakout", "breakout", s_keltner_squeeze),
    "vwap_revert": ("VWAP reversion 20", "mean reversion", s_vwap_revert),
    "adx_trend": ("ADX + DI trend", "trend", s_adx_trend),
    "aroon": ("Aroon trend", "trend", s_aroon),
    "stochrsi": ("Stoch-RSI cross", "mean reversion", s_stochrsi),
    "cci_revert": ("CCI reversion", "mean reversion", s_cci_revert),
    "mfi_revert": ("MFI reversion", "mean reversion", s_mfi_revert),
    "hma_trend": ("Hull MA 55 trend", "trend", s_hma_trend),
    "kama_trend": ("KAMA trend", "trend", s_kama_trend),
    "vortex": ("Vortex 14", "trend", s_vortex),
    # the desk's strategy library: until now it only showed on the desk, with no route to the bots
    "lib_volume_breakout": ("Library: volume breakout", "breakout", _library("VolumeBreakoutStrategy")),
    "lib_shrink_pullback": ("Library: shrink pullback", "trend", _library("ShrinkPullbackStrategy")),
    "lib_box_oscillation": ("Library: box oscillation", "mean reversion", _library("BoxOscillationStrategy")),
    "lib_vol_compression": ("Library: volatility compression breakout", "breakout",
                            _library("VolatilityCompressionBreakoutStrategy")),
    # deep-research additions: trailing exits on existing entries, then untested-on-crypto pattern rules
    "donchian_chandelier": ("Donchian 20 + Chandelier exit", "trend", s_donchian_chandelier),
    "tsmom_chandelier": ("TS momentum + Chandelier exit", "momentum", s_tsmom_chandelier),
    "ema_atr_trail": ("EMA cross + ATR trailing stop", "trend", s_ema_atr_trail),
    "nr7": ("NR7 breakout (Crabel)", "breakout", s_nr7),
    "inside_bar": ("Inside-bar breakout", "breakout", s_inside_bar),
    "connors_rsi": ("Connors RSI < 10", "mean reversion", s_connors_rsi),
    "zscore_revert": ("Z-score reversion 20", "mean reversion", s_zscore_revert),
    "turn_of_month": ("Turn of month (daily)", "seasonality", s_turn_of_month),
    "utc_orb": ("UTC-day opening-range breakout", "breakout", s_utc_orb),
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
        # PSR, MinTRL, Ulcer/UPI, Omega, tail ratio, gain-to-pain, SQN, K-ratio, MAR (core/quant/metrics_extra.py)
        **_extra_metrics(rets, curve, trades, bars_per_year),
    }


def _extra_metrics(rets, curve, trades, bars_per_year):
    from core.quant.metrics_extra import full_report
    try:
        return full_report(rets, curve, trades, bars_per_year)
    except Exception:   # a metric must never break a backtest
        return {}


def run_lab(c: Candles, interval: str = "1d", fee_bps: float = 10.0, only: Optional[List[str]] = None,
            catalog: bool = True) -> Dict[str, object]:
    if interval not in INTERVALS:
        raise ValueError("Unsupported interval")
    if len(c) < 150:
        return {"status": "INSUFFICIENT_DATA", "bars": len(c), "required": 150}
    bpy = YEAR_SECONDS / INTERVALS[interval]
    bh_curve = [b["close"] / c[0]["open"] for b in c]
    bh = {"total_return": c[-1]["close"] / c[0]["open"] - 1,
          "max_drawdown": min(v / max(bh_curve[:i + 1]) - 1 for i, v in enumerate(bh_curve))}
    rows, positions = [], {}
    for key, (label, family, fn) in STRATEGIES.items():
        if only and key not in only:
            continue
        try:
            pos = fn(c)
            m = backtest(c, pos, fee_bps, bpy)
        except Exception as exc:  # one broken strategy never takes the lab down
            rows.append({"key": key, "label": label, "family": family, "error": type(exc).__name__})
            continue
        positions[key] = pos
        m["beats_hold"] = m["total_return"] > bh["total_return"]
        rows.append({"key": key, "label": label, "family": family, **m})
    ok = [r for r in rows if "error" not in r]
    m_tests = max(1, len(ok))
    for r in ok:  # Bonferroni across all strategies tested on the same data
        r["significant"] = r["p_value"] is not None and r["p_value"] < 0.05 / m_tests
    try:
        gate = gate_candidates(c, positions, interval, fee_bps)
    except Exception as exc:  # the gate failing must never look like a pass
        gate = {"status": "ERROR", "error": type(exc).__name__, "candidates": {}}
    for r in ok:
        r["gate"] = gate["candidates"].get(r["key"]) or {"passed": False, "reasons": ["not evaluated"]}
    ok.sort(key=lambda r: -r["sharpe"])
    step = max(1, len(c) // 300)
    out = {"status": "OK", "interval": interval, "bars": len(c), "fee_bps": fee_bps,
           "from": c[0]["open_time"], "to": c[-1]["open_time"], "buy_hold": bh,
           "times": [int(b["open_time"]) for b in c[::step]],
           "buy_hold_curve": bh_curve[::step],
           "results": [{**r, "curve": r["curve"][::step]} for r in ok] + [r for r in rows if "error" in r],
           "gate": {k: v for k, v in gate.items() if k != "candidates"},
           "method": __doc__.split("Strategies and formulas", 1)[1].strip()}
    if catalog:
        out["catalog"] = _catalog(c)
    return out


def _catalog(c: Candles) -> Dict[str, object]:
    try:
        from cryptoscope.desk.indicator_catalog import catalog_summary, compute_catalog
        return catalog_summary(compute_catalog(c))
    except Exception as exc:  # the catalog is informational; the lab still runs without it
        return {"status": "UNAVAILABLE", "error": type(exc).__name__}


# --------------------------------------------------------------------------- promotion gate
GATE = {"min_oos_trades": 100, "max_dsr_p": 0.05, "max_pbo": 0.30, "min_expectancy": 0.0,
        "min_fee_bps": 10.0, "profile": "SCALP", "cpcv_groups": 10}


def gate_candidates(c: Candles, positions: Dict[str, Sequence[int]], interval: str, fee_bps: float) -> Dict[str, Any]:
    """Out-of-sample gate for every candidate (see the module docstring, "Promotion gate").

    Entries are the bars where a candidate's position turns 0 -> 1. Each becomes the bracket trade the
    bot would place: StrategyBot.bracket(profile, ATR14 / close) for target and stop, the profile's
    time limit converted to this interval's bars, fee >= 10 bp per side. One PBO is computed for the
    whole candidate set (the selection process is what overfits), and the DSR is deflated by the
    number of candidates tried.
    """
    n, iv = len(c), INTERVALS[interval]
    fee = max(float(fee_bps), GATE["min_fee_bps"]) / 10000
    o, h, lo, cl = ([b[k] for b in c] for k in ("open", "high", "low", "close"))
    a = atr(c, 14)
    stops, targets, has_atr = [0.0] * n, [0.0] * n, [False] * n
    horizon15 = bracket(GATE["profile"], 0.01)[2]
    for i in range(n):
        if a[i] is not None and cl[i] > 0:
            stops[i], targets[i], _ = bracket(GATE["profile"], a[i] / cl[i])
            has_atr[i] = True
    hbars = max(1, round(horizon15 * 900 / iv))
    groups = group_bounds(n, GATE["cpcv_groups"])
    group_of = np.zeros(n, dtype=int)
    for g, (s, e) in enumerate(groups):
        group_of[s:e] = g
    keys = list(positions)
    mat = np.zeros((n, max(1, len(keys))))
    label_end = np.arange(n)
    per: Dict[str, Dict[str, Any]] = {}
    for j, key in enumerate(keys):
        pos = positions[key]
        sig = [1 if t > 0 and pos[t] == 1 and pos[t - 1] == 0 and has_atr[t] else 0 for t in range(n)]
        trades = triple_barrier_labels(o, h, lo, cl, sig, stops, targets, hbars, fee=fee)
        oos = [t for t in trades if group_of[t["signal"]] == group_of[t["exit"]]]
        for t in trades:
            mat[t["signal"], j] = t["ret"]
            label_end[t["signal"]] = max(label_end[t["signal"]], t["exit"])
        rets = [t["ret"] for t in oos]
        per[key] = {"trades": len(trades), "oos_trades": len(oos), "rets": rets,
                    "expectancy": float(np.mean(rets)) if rets else None,
                    "win_rate": (sum(r > 0 for r in rets) / len(rets)) if rets else None,
                    "targets": sum(t["barrier"] == 1 for t in oos), "stops": sum(t["barrier"] == -1 for t in oos),
                    "timeouts": sum(t["barrier"] == 0 for t in oos)}
    pbo = None
    splits = 0
    if len(keys) >= 2:
        res = probability_of_backtest_overfitting(mat, n_groups=GATE["cpcv_groups"], label_end=label_end,
                                                  embargo=max(hbars, math.ceil(0.01 * n)))
        pbo, splits = res["pbo"], res["splits"]
    srs = [float(np.mean(p["rets"]) / np.std(p["rets"], ddof=1)) for p in per.values()
           if len(p["rets"]) >= 4 and np.std(p["rets"], ddof=1) > 1e-12]
    var_sr = float(np.var(srs, ddof=1)) if len(srs) >= 2 else None
    out: Dict[str, Dict[str, Any]] = {}
    for key, p in per.items():
        d = deflated_sharpe(p.pop("rets"), n_trials=len(keys), var_sharpe=var_sr)
        reasons = []
        if p["oos_trades"] < GATE["min_oos_trades"]:
            reasons.append(f"{p['oos_trades']} OOS trades < {GATE['min_oos_trades']}")
        if d["p_value"] >= GATE["max_dsr_p"]:
            reasons.append(f"DSR p {d['p_value']:.2f} >= {GATE['max_dsr_p']}")
        if pbo is None or pbo >= GATE["max_pbo"]:
            reasons.append("PBO n/a" if pbo is None else f"PBO {pbo:.2f} >= {GATE['max_pbo']}")
        if p["expectancy"] is None or p["expectancy"] <= GATE["min_expectancy"]:
            reasons.append("expectancy after fees <= 0")
        out[key] = {**p, "sharpe_per_trade": d["sharpe"], "dsr": d["dsr"], "dsr_p": d["p_value"], "pbo": pbo,
                    "passed": not reasons, "reasons": reasons}
    return {"status": "OK", "candidates": out, "pbo": pbo, "pbo_splits": splits, "n_candidates": len(keys),
            "horizon_bars": hbars, "fee_bps": round(fee * 10000, 4), "thresholds": {k: GATE[k] for k in
            ("min_oos_trades", "max_dsr_p", "max_pbo", "min_expectancy", "profile")}}


PROMOTED_PATH = Path(__file__).resolve().parents[2] / "work" / "runtime" / "promoted_strategies.json"
_promo_lock = threading.Lock()


def record_promotions(result: Dict[str, Any], symbol: str, path: Optional[Path] = None) -> Dict[str, Any]:
    """Write this run's gate passes to promoted_strategies.json, replacing earlier entries for the same
    symbol and interval (a strategy that stops passing is demoted). Returns the file's new content."""
    path = Path(path or PROMOTED_PATH)
    if result.get("status") != "OK" or result.get("gate", {}).get("status") != "OK":
        return {"promoted": load_promoted_strategies(path)}
    interval = result["interval"]
    passed = [{"symbol": symbol, "interval": interval, "strategy": r["key"], "label": r["label"],
               "family": r["family"], "fee_bps": result["gate"]["fee_bps"], "bars": result["bars"],
               "from": result["from"], "to": result["to"], "promoted_at": time.time(),
               **{k: r["gate"][k] for k in ("oos_trades", "expectancy", "win_rate", "dsr_p", "pbo")}}
              for r in result.get("results", []) if r.get("gate", {}).get("passed")]
    with _promo_lock:
        keep = [e for e in load_promoted_strategies(path)
                if not (e.get("symbol") == symbol and e.get("interval") == interval)]
        doc = {"updated_at": time.time(), "gate": result["gate"]["thresholds"], "promoted": keep + passed}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:  # a read-only disk must not take the Lab page down
            return {**doc, "error": type(exc).__name__}
    return doc


def load_promoted_strategies(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Promoted strategies (symbol, interval, strategy key, gate metrics); [] when none or unreadable."""
    try:
        doc = json.loads(Path(path or PROMOTED_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = doc.get("promoted") if isinstance(doc, dict) else None
    return [e for e in items if isinstance(e, dict) and e.get("strategy") in STRATEGIES] if isinstance(items, list) else []
