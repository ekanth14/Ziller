"""Long-only cross-sectional momentum rotation (research tool; the deep-research report's #5 priority).

Evidence: Liu, Tsyvinski & Wu (J. Finance 2022) and Dobrynskaya find 1-4 week cross-sectional momentum
in crypto, but much of the published alpha comes from the SHORT leg and shrinks after costs, so this
long-only spot version must prove itself on our own post-2022 data before it could ever drive trading.

Rules (pre-registered, not tuned):
- Universe: the N most liquid USDT spot coins (operator exclusions applied), daily closes.
- Every `rebalance_days`: score = mean over lookbacks (7, 14, 21, 28 days) of each coin's cross-sectional
  percentile rank of its trailing return. Only coins with a positive average trailing return qualify.
- Hold up to k coins, equal weight. Turnover buffer: keep a holding while its rank is within the top 2k;
  fill empty slots with the best-ranked new coins.
- BTC gate: hold nothing (cash/USDT) while BTC closes below its 50-day SMA.
- Costs: fee_bps per side on every change in weight (turnover-based).
Decisions use closes up to day t; positions earn from t to t+1 (no lookahead).
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Sequence

LOOKBACKS = (7, 14, 21, 28)


def _pct_ranks(values: Dict[str, float]) -> Dict[str, float]:
    order = sorted(values, key=lambda s: values[s])
    n = len(order)
    return {s: (i + 0.5) / n for i, s in enumerate(order)} if n else {}


def rotation_backtest(closes: Dict[str, Sequence[Optional[float]]], btc: Sequence[float], times: Sequence[float],
                      k: int = 3, rebalance_days: int = 7, fee_bps: float = 10.0, gate_sma: int = 50,
                      lookbacks: Sequence[int] = LOOKBACKS, oos_split: float = 0.7,
                      dollar_volume: Optional[Dict[str, Sequence[Optional[float]]]] = None,
                      top_liquid: Optional[int] = None, weighting: str = "equal") -> Dict[str, Any]:
    """`closes[sym]` and `btc` are aligned daily closes over `times` (None before a coin listed).

    With `dollar_volume` + `top_liquid`, the tradable universe at each rebalance is the `top_liquid` coins
    by trailing 30-day dollar volume AT THAT DATE (point-in-time), not by the current volume.

    `weighting` (QuantConnect LEAN portfolio-construction ideas): "equal" (EqualWeighting), "inverse_vol"
    (naive risk parity: weight ~ 1 / 20-day volatility) or "score" (ConfidenceWeighted: weight ~ rank score)."""
    if weighting not in {"equal", "inverse_vol", "score"}:
        raise ValueError("weighting must be equal, inverse_vol or score")
    from core.quant.metrics_extra import full_report
    syms = list(closes)
    T, fee, start = len(times), fee_bps / 10000, max(max(lookbacks), gate_sma)
    w: Dict[str, float] = {}
    eq, curve, rets, entries, trade_rets = 1.0, [1.0], [], 0, []
    opened: Dict[str, float] = {}
    holdings_log = []
    for t in range(start, T - 1):
        if (t - start) % rebalance_days == 0:
            btc_ok = btc[t] > sum(btc[t - gate_sma + 1:t + 1]) / gate_sma
            target: List[str] = []
            scores: Dict[str, float] = {}
            if btc_ok:
                scores, avg_ret = {}, {}
                per_lb = []
                pool = [s for s in syms if closes[s][t] and closes[s][t - max(lookbacks)]]
                if dollar_volume and top_liquid:
                    dv = {s: sum(v for v in dollar_volume[s][t - 29:t + 1] if v) for s in pool}
                    pool = sorted(pool, key=lambda s: -dv[s])[:top_liquid]
                for lb in lookbacks:
                    r = {s: closes[s][t] / closes[s][t - lb] - 1 for s in pool
                         if closes[s][t - lb] and closes[s][t - lb] > 0 and closes[s][t]}
                    per_lb.append(_pct_ranks(r))
                    for s, v in r.items():
                        avg_ret.setdefault(s, []).append(v)
                for s in pool:
                    if all(s in pr for pr in per_lb):
                        scores[s] = sum(pr[s] for pr in per_lb) / len(per_lb)
                ranked = [s for s in sorted(scores, key=lambda s: -scores[s]) if sum(avg_ret[s]) / len(avg_ret[s]) > 0]
                keep = [s for s in w if s in ranked[:2 * k]]
                target = (keep + [s for s in ranked if s not in keep])[:k]
            new_w = _weights(target, weighting, closes, t, scores if btc_ok else {})
            turnover = sum(abs(new_w.get(s, 0) - w.get(s, 0)) for s in set(w) | set(new_w))
            for s in set(w) - set(new_w):                      # exits -> per-trade return
                trade_rets.append(closes[s][t] / opened.pop(s) * (1 - fee) ** 2 - 1)
            for s in set(new_w) - set(w):
                opened[s], entries = closes[s][t], entries + 1
            eq *= 1 - fee * turnover
            w = new_w
            holdings_log.append({"time": times[t], "holdings": list(w), "btc_gate": btc_ok})
        r = sum(wt * (closes[s][t + 1] / closes[s][t] - 1) for s, wt in w.items())
        eq *= 1 + r
        curve.append(eq)
        rets.append(r)
    for s, px in opened.items():                               # mark open holdings
        trade_rets.append(closes[s][T - 1] / px * (1 - fee) - 1)

    def stats(rr, cv):
        if len(rr) < 2:
            return {}
        m = sum(rr) / len(rr)
        sd = math.sqrt(sum((x - m) ** 2 for x in rr) / (len(rr) - 1))
        peak, mdd = cv[0], 0.0
        for v in cv:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
        yrs = len(rr) / 365
        return {"total_return": cv[-1] / cv[0] - 1, "cagr": (cv[-1] / cv[0]) ** (1 / yrs) - 1 if yrs > 0 and cv[-1] > 0 else None,
                "sharpe": m / sd * math.sqrt(365) if sd else None, "max_drawdown": mdd}

    split = int(len(rets) * oos_split)
    oos_rets, oos_curve = rets[split:], curve[split:]
    bench = [1.0]
    for t in range(start, T - 1):    # equal-weight, daily-rebalanced basket of every coin trading at t
        live = [s for s in syms if closes[s][t] and closes[s][t + 1]]
        bench.append(bench[-1] * (1 + (sum(closes[s][t + 1] / closes[s][t] - 1 for s in live) / len(live) if live else 0)))
    btc_curve = [btc[t] / btc[start] for t in range(start, T)]
    oos = stats(oos_rets, oos_curve)
    extra = full_report(oos_rets, oos_curve, trade_rets, 365)
    oos_entries = sum(1 for h0, h1 in zip(holdings_log, holdings_log[1:])
                      for s in set(h1["holdings"]) - set(h0["holdings"]) if h1["time"] >= times[start + split])
    checks = {"oos_entries_100": oos_entries >= 100, "psr_95": (extra.get("psr") or 0) >= 0.95,
              "positive_oos_after_fees": (oos.get("total_return") or 0) > 0}
    return {"params": {"k": k, "rebalance_days": rebalance_days, "fee_bps": fee_bps, "gate_sma": gate_sma,
                       "lookbacks": list(lookbacks), "universe": syms, "top_liquid": top_liquid,
                       "weighting": weighting},
            "full": stats(rets, curve), "oos": oos, "oos_metrics": extra, "entries": entries, "oos_entries": oos_entries,
            "checks": checks, "passes": all(checks.values()),
            "curve": [{"time": times[start + i], "equity": round(v, 6)} for i, v in enumerate(curve)],
            "benchmark": [{"time": times[start + i], "equity": round(v, 6)} for i, v in enumerate(bench)],
            "btc": [{"time": times[start + i], "equity": round(v, 6)} for i, v in enumerate(btc_curve)],
            "oos_from": times[start + split] if start + split < T else None,
            "last_holdings": holdings_log[-1] if holdings_log else None}


def _weights(target: List[str], weighting: str, closes, t: int, scores: Dict[str, float]) -> Dict[str, float]:
    if not target:
        return {}
    if weighting == "inverse_vol":
        raw = {}
        for s in target:
            px = [closes[s][i] for i in range(max(1, t - 20), t + 1) if closes[s][i] and closes[s][i - 1]]
            r = [px[i] / px[i - 1] - 1 for i in range(1, len(px))]
            sd = math.sqrt(sum((x - sum(r) / len(r)) ** 2 for x in r) / (len(r) - 1)) if len(r) > 2 else 0.0
            raw[s] = 1.0 / sd if sd > 0 else 0.0
    elif weighting == "score":
        raw = {s: max(0.0, scores.get(s, 0.0)) for s in target}
    else:
        raw = {s: 1.0 for s in target}
    total = sum(raw.values())
    return {s: v / total for s, v in raw.items()} if total > 0 else {s: 1.0 / len(target) for s in target}


_CACHE: Dict[tuple, tuple] = {}


def run_rotation(n: int = 20, k: int = 3, days: int = 1000, fee_bps: float = 10.0, pool_size: int = 60,
                 weighting: str = "equal",
                 tickers: Optional[Callable[[], list]] = None, klines: Optional[Callable[..., list]] = None) -> Dict[str, Any]:
    """Fetch the universe from Binance (daily klines) and run the backtest. Cached for an hour."""
    from cryptoscope.desk.feed import fetch_klines
    from cryptoscope.desk.scanner import LEVERAGED, STABLE_BASES, fetch_24h_tickers
    from cryptoscope.trading_universe import excluded_symbols
    key = (n, k, days, fee_bps, weighting)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    tickers, klines = tickers or fetch_24h_tickers, klines or fetch_klines
    blocked = excluded_symbols()
    rows = [t for t in tickers() if t["symbol"].endswith("USDT") and t["symbol"] not in blocked
            and t["symbol"][:-4] not in STABLE_BASES and not t["symbol"][:-4].endswith(LEVERAGED)]
    # Candidate pool: coins listed now (delisted coins are unavailable, a residual survivorship bias that is
    # reported in the result). The traded universe is chosen point-in-time inside the backtest.
    universe = [t["symbol"] for t in sorted(rows, key=lambda t: -float(t["quoteVolume"]))[:pool_size]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        data = dict(zip(universe + ["BTCUSDT"], pool.map(lambda s: _safe(klines, s, days), universe + ["BTCUSDT"])))
    btc = data.pop("BTCUSDT")
    if not btc:
        return {"status": "UNAVAILABLE", "error": "BTC history unavailable"}
    times = [b["open_time"] for b in btc]
    aligned, dvol = {}, {}
    for s, bars in data.items():
        m = {b["open_time"]: b for b in bars or []}
        if len(m) < 60 or times[-1] not in m:                   # too short, or no longer trading
            continue
        last, series, vols = None, [], []
        for t in times:
            b = m.get(t)
            last = b["close"] if b else last
            series.append(last)
            vols.append(b["close"] * b["volume"] if b else None)
        aligned[s], dvol[s] = series, vols
    if len(aligned) < max(2 * k, 6):
        return {"status": "UNAVAILABLE", "error": f"only {len(aligned)} coins with full history"}
    res = {"status": "OK", **rotation_backtest(aligned, [b["close"] for b in btc], times, k=k, fee_bps=fee_bps,
                                               dollar_volume=dvol, top_liquid=n, weighting=weighting),
           "skipped": [s for s in universe if s not in aligned],
           "caveats": ["Candidate pool is coins listed now; delisted coins are missing (survivorship bias "
                       "flatters results).", "The tradable universe is picked point-in-time by trailing "
                       "30-day dollar volume.", "Research only: the bot fleet does not trade this rotation."]}
    _CACHE[key] = (time.time(), res)
    return res


def _safe(fn, s, days):
    try:
        return fn(s, "1d", days)
    except Exception:
        return []
