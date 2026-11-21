"""Performance statistics the Lab and P&L pages were missing (deep-research report, 2026-11-21).

All functions take plain lists and never raise on short or flat input (they return None instead).
Conventions, stated because sources disagree:
- Per-period returns `r` (e.g. per 15m bar or per day), NOT annualised, unless a function says so.
- Kurtosis is RAW (normal = 3) in PSR / MinTRL (Bailey & Lopez de Prado 2012).
- Sortino divides downside squares by the TOTAL number of periods (a common bug divides by losers only).
- SQN uses sqrt(min(N, 100)) (Van Tharp's cap, so large samples are not inflated).
- K-ratio is Kestner's 2003 variant: slope / (standard error of slope * sqrt(n)), on log equity.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import List, Optional, Sequence

_N = NormalDist()


def _moments(r: Sequence[float]):
    n = len(r)
    if n < 3:
        return None
    m = sum(r) / n
    var = sum((x - m) ** 2 for x in r) / n
    if var <= 0:
        return None
    sd = math.sqrt(var)
    skew = sum((x - m) ** 3 for x in r) / n / sd ** 3
    kurt = sum((x - m) ** 4 for x in r) / n / sd ** 4          # raw kurtosis
    sr = m / math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1))  # per-period Sharpe (sample sd)
    return n, sr, skew, kurt


def probabilistic_sharpe(r: Sequence[float], sr_benchmark: float = 0.0) -> Optional[float]:
    """PSR = P(true Sharpe > benchmark) given skew and fat tails. Bailey & Lopez de Prado (2012).

    PSR = Phi( (SR - SR*) * sqrt(n - 1) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2) ),  SR per period, g4 raw kurtosis.
    """
    mo = _moments(r)
    if not mo:
        return None
    n, sr, g3, g4 = mo
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr * sr
    if den <= 0:
        return None
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(den))


def min_track_record_length(r: Sequence[float], sr_benchmark: float = 0.0, confidence: float = 0.95) -> Optional[float]:
    """Periods needed before the observed Sharpe beats `sr_benchmark` at `confidence`. None if SR <= benchmark.

    MinTRL = 1 + (1 - g3*SR + (g4 - 1)/4 * SR^2) * (z_conf / (SR - SR*))^2
    """
    mo = _moments(r)
    if not mo:
        return None
    _, sr, g3, g4 = mo
    if sr <= sr_benchmark:
        return None
    return 1 + (1 - g3 * sr + (g4 - 1) / 4 * sr * sr) * (_N.inv_cdf(confidence) / (sr - sr_benchmark)) ** 2


def sortino(r: Sequence[float], periods_per_year: float, target: float = 0.0) -> Optional[float]:
    if len(r) < 2:
        return None
    dd = math.sqrt(sum(min(0.0, x - target) ** 2 for x in r) / len(r))
    return (sum(r) / len(r) - target) / dd * math.sqrt(periods_per_year) if dd else None


def ulcer_index(curve: Sequence[float]) -> Optional[float]:
    """Peter Martin's Ulcer Index: RMS of percentage drawdowns from the running peak (in %)."""
    if len(curve) < 2:
        return None
    peak, sq = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        sq += (100.0 * (v / peak - 1)) ** 2 if peak > 0 else 0.0
    return math.sqrt(sq / len(curve))


def ulcer_performance_index(curve: Sequence[float], periods_per_year: float, rf: float = 0.0) -> Optional[float]:
    """UPI (Martin ratio) = (annualised return % - rf %) / Ulcer Index."""
    ui = ulcer_index(curve)
    if not ui or curve[0] <= 0 or curve[-1] <= 0:
        return None
    years = (len(curve) - 1) / periods_per_year
    if years <= 0:
        return None
    ann = (curve[-1] / curve[0]) ** (1 / years) - 1
    return (100.0 * ann - 100.0 * rf) / ui


def omega_ratio(r: Sequence[float], threshold: float = 0.0) -> Optional[float]:
    """Keating & Shadwick: sum of gains above the threshold / sum of losses below it."""
    up = sum(max(0.0, x - threshold) for x in r)
    dn = sum(max(0.0, threshold - x) for x in r)
    return up / dn if dn > 0 else None


def tail_ratio(r: Sequence[float]) -> Optional[float]:
    """|95th percentile| / |5th percentile| of returns (>1: right tail fatter than left)."""
    if len(r) < 20:
        return None
    s = sorted(r)
    q = lambda p: s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))]  # noqa: E731
    lo = abs(q(0.05))
    return abs(q(0.95)) / lo if lo > 0 else None


def gain_to_pain(r: Sequence[float]) -> Optional[float]:
    """Schwager: sum of all returns / |sum of negative returns|."""
    pain = -sum(x for x in r if x < 0)
    return sum(r) / pain if pain > 0 else None


def sqn(trade_returns: Sequence[float]) -> Optional[float]:
    """Van Tharp's System Quality Number = sqrt(min(N, 100)) * mean / sd of per-trade returns."""
    n = len(trade_returns)
    if n < 2:
        return None
    m = sum(trade_returns) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in trade_returns) / (n - 1))
    return math.sqrt(min(n, 100)) * m / sd if sd > 0 else None


def k_ratio(curve: Sequence[float]) -> Optional[float]:
    """Kestner (2003): OLS slope of log equity on time / (standard error of slope * sqrt(n))."""
    y = [math.log(v) for v in curve if v > 0]
    n = len(y)
    if n < 3 or n != len(curve):
        return None
    xm, ym = (n - 1) / 2, sum(y) / n
    sxx = sum((i - xm) ** 2 for i in range(n))
    b = sum((i - xm) * (v - ym) for i, v in enumerate(y)) / sxx
    resid = sum((v - (ym + b * (i - xm))) ** 2 for i, v in enumerate(y))
    se = math.sqrt(resid / (n - 2) / sxx) if resid > 0 else 0.0
    if se <= 1e-9 * max(abs(b), 1e-12):    # a perfectly straight curve: the ratio is undefined, not huge
        return None
    return b / (se * math.sqrt(n))


def calmar(curve: Sequence[float], periods_per_year: float) -> Optional[float]:
    """MAR / Calmar on the full history: CAGR / |max drawdown| (Calmar proper uses the last 36 months)."""
    if len(curve) < 2 or curve[0] <= 0 or curve[-1] <= 0:
        return None
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    years = (len(curve) - 1) / periods_per_year
    if years <= 0 or mdd >= 0:
        return None
    return ((curve[-1] / curve[0]) ** (1 / years) - 1) / -mdd


def frac_diff_weights(d: float, threshold: float = 1e-4, max_len: int = 10_000) -> List[float]:
    """Fixed-width fractional-differencing weights (Lopez de Prado, AFML ch. 5):
    w_0 = 1, w_k = -w_{k-1} * (d - k + 1) / k, truncated once |w_k| < threshold."""
    w = [1.0]
    for k in range(1, max_len):
        nxt = -w[-1] * (d - k + 1) / k
        if abs(nxt) < threshold:
            break
        w.append(nxt)
    return w


def frac_diff(series: Sequence[float], d: float, threshold: float = 1e-4) -> List[Optional[float]]:
    """FFD series: memory-preserving, (more) stationary transform; None until the window is full."""
    w = frac_diff_weights(d, threshold)
    out: List[Optional[float]] = [None] * len(series)
    for t in range(len(w) - 1, len(series)):
        out[t] = sum(w[k] * series[t - k] for k in range(len(w)))
    return out


def full_report(rets: Sequence[float], curve: Sequence[float], trade_returns: Sequence[float],
                periods_per_year: float) -> dict:
    """Every extra metric at once (None where a metric is undefined for this sample)."""
    psr = probabilistic_sharpe(rets)
    mtrl = min_track_record_length(rets)
    return {"psr": psr, "min_trl_periods": mtrl,
            "min_trl_met": (mtrl is not None and len(rets) >= mtrl),
            "sortino_total_n": sortino(rets, periods_per_year), "mar": calmar(curve, periods_per_year),
            "ulcer_index": ulcer_index(curve), "upi": ulcer_performance_index(curve, periods_per_year),
            "omega": omega_ratio(rets), "tail_ratio": tail_ratio(rets), "gain_to_pain": gain_to_pain(rets),
            "sqn": sqn(trade_returns), "k_ratio": k_ratio(curve)}


# --------------------------------------------------------------------------- QuantConnect LEAN statistics
# Ideas from LEAN's PortfolioStatistics / TradeStatistics / Report (Apache-2.0), reimplemented here.

def capm_stats(rets: Sequence[float], bench: Sequence[float], periods_per_year: float, rf: float = 0.0) -> dict:
    """Beta = cov(r, b)/var(b); Alpha = annR - (rf + beta*(annB - rf)); Treynor = (annR - rf)/beta;
    tracking error = annualised sd(r - b); information ratio = (annR - annB)/TE."""
    n = min(len(rets), len(bench))
    if n < 10:
        return {}
    r, b = list(rets[:n]), list(bench[:n])
    mr, mb = sum(r) / n, sum(b) / n
    vb = sum((x - mb) ** 2 for x in b) / (n - 1)
    cov = sum((x - mr) * (y - mb) for x, y in zip(r, b)) / (n - 1)
    beta = cov / vb if vb > 0 else None
    ann_r, ann_b = mr * periods_per_year, mb * periods_per_year
    diff = [x - y for x, y in zip(r, b)]
    md = sum(diff) / n
    te = math.sqrt(sum((d - md) ** 2 for d in diff) / (n - 1) * periods_per_year)
    return {"beta": beta,
            "alpha": (ann_r - (rf + beta * (ann_b - rf))) if beta is not None else None,
            "treynor": ((ann_r - rf) / beta) if beta else None,
            "tracking_error": te, "information_ratio": ((ann_r - ann_b) / te) if te > 0 else None}


def var_parametric(rets: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    """One-period normal VaR as a positive loss fraction (LEAN ValueAtRisk95/99 use the last 252 days)."""
    r = list(rets[-252:])
    if len(r) < 20:
        return None
    m = sum(r) / len(r)
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    return max(0.0, -(m + _N.inv_cdf(1 - confidence) * sd))


def trade_stats_lean(trades: Sequence[float]) -> dict:
    """Streaks, largest win/loss, profit-loss ratio and LEAN's expectancy = WinRate*PLR - LossRate."""
    if not trades:
        return {}
    wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
    best = cur = 0
    worst = curl = 0
    for t in trades:
        cur, curl = (cur + 1, 0) if t > 0 else (0, curl + 1)
        best, worst = max(best, cur), max(worst, curl)
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    plr = avg_w / abs(avg_l) if avg_l else None
    wr = len(wins) / len(trades)
    return {"max_consecutive_wins": best, "max_consecutive_losses": worst, "largest_win": max(trades),
            "largest_loss": min(trades), "profit_loss_ratio": plr,
            "lean_expectancy": (wr * plr - (1 - wr)) if plr is not None else None}


def drawdown_periods(curve: Sequence[float], times: Sequence[float], top: int = 5) -> List[dict]:
    """The `top` worst peak-to-trough drawdowns with start, trough, recovery time and depth (LEAN Report)."""
    out, peak_i, i, n = [], 0, 1, len(curve)
    while i < n:
        if curve[i] >= curve[peak_i]:
            peak_i, i = i, i + 1
            continue
        trough_i, j = i, i
        while j < n and curve[j] < curve[peak_i]:
            if curve[j] < curve[trough_i]:
                trough_i = j
            j += 1
        out.append({"start": times[peak_i], "trough": times[trough_i], "end": times[j] if j < n else None,
                    "depth": curve[trough_i] / curve[peak_i] - 1, "bars": (j if j < n else n - 1) - peak_i,
                    "recovered": j < n})
        peak_i, i = j if j < n else n - 1, j + 1
    return sorted(out, key=lambda d: d["depth"])[:top]


def monthly_returns(curve: Sequence[float], times: Sequence[float]) -> List[dict]:
    """Compounded return per calendar month (UTC) from an equity curve (LEAN monthly returns heatmap)."""
    import datetime as dt
    out, last_eq, cur_key, start_eq = [], None, None, None
    for eq, t in zip(curve, times):
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        key = (d.year, d.month)
        if key != cur_key:
            if cur_key is not None:
                out.append({"year": cur_key[0], "month": cur_key[1], "ret": last_eq / start_eq - 1})
            cur_key, start_eq = key, (last_eq if last_eq is not None else eq)
        last_eq = eq
    if cur_key is not None and start_eq:
        out.append({"year": cur_key[0], "month": cur_key[1], "ret": last_eq / start_eq - 1})
    return out


def rolling_sharpe(rets: Sequence[float], times: Sequence[float], window: int, periods_per_year: float,
                   max_points: int = 150) -> List[dict]:
    """Rolling annualised Sharpe over `window` periods, down-sampled to at most `max_points` points."""
    pts = []
    step = max(1, (len(rets) - window) // max_points) if len(rets) > window else 1
    for i in range(window, len(rets) + 1, step):
        w = rets[i - window:i]
        m = sum(w) / window
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / (window - 1))
        pts.append({"time": times[i - 1], "value": (m / sd * math.sqrt(periods_per_year)) if sd else 0.0})
    return pts
