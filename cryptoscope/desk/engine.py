"""Action Desk engine: rule models vote on daily bars, a PM aggregates, a paper book executes.

Everything is deterministic and computed from real exchange daily candles:
- four rule models (trend, momentum, volume, drawdown) each vote +1 / 0 / -1 per session
- the PM turns the weighted vote score into BUY / HOLD / SELL (long-only spot, 1.00x or flat)
- decisions made on a bar's close fill at the NEXT bar's open (no lookahead), fee per side
- models are scored against the realised return of the following sessions

No synthetic data is ever generated here. With too little history the desk reports
INSUFFICIENT_DATA instead of filling gaps.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

MODELS = (
    # key, label, weight, rule description
    ("trend", "Trend", 1.2, "SMA10>SMA30"),
    ("momentum", "Momentum", 1.0, "r20 vs ±3%"),
    ("volume", "Volume", 0.8, "vol vs 1.40x avg20"),
    ("drawdown", "Drawdown", 0.6, "dd in -25%..-5%"),
)
WEIGHTS = {key: weight for key, _label, weight, _rule in MODELS}
MAX_SCORE = sum(WEIGHTS.values())

BUY_SCORE = 1.2
SELL_SCORE = -1.2
MOMENTUM_BAND = 0.03
VOLUME_SPIKE = 1.40
DD_LOW, DD_HIGH = -0.25, -0.05
MIN_BARS = 60
SCORE_HORIZON = 5
BARS_PER_YEAR = 365  # daily bars; crypto trades every day
# Supported chart/decision intervals (Binance kline codes -> seconds)
INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
YEAR_SECONDS = 365 * 86400


# --------------------------------------------------------------------------- indicators
def _sma(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        out.append(run / n if i >= n - 1 else None)
    return out


def _ema(values: Sequence[float], n: int) -> List[float]:
    k = 2.0 / (n + 1.0)
    out: List[float] = []
    for i, v in enumerate(values):
        out.append(v if i == 0 else k * v + (1 - k) * out[-1])
    return out


def _rolling_std(values: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(len(values)):
        if i < n - 1:
            out.append(None)
            continue
        win = values[i - n + 1:i + 1]
        m = sum(win) / n
        out.append(math.sqrt(sum((x - m) ** 2 for x in win) / n))
    return out


def _rsi(closes: Sequence[float], n: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None]
    avg_g = avg_l = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            avg_g += g / n
            avg_l += l / n
            out.append(None if i < n else (100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)))
        else:
            avg_g = (avg_g * (n - 1) + g) / n
            avg_l = (avg_l * (n - 1) + l) / n
            out.append(100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l))
    return out


def _atr(highs, lows, closes, n: int = 14) -> List[Optional[float]]:
    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return _sma(trs, n)


def indicators(candles: Sequence[Dict[str, float]], bars_per_year: float = BARS_PER_YEAR) -> Dict[str, list]:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] for c in candles]
    sma10, sma30, sma20 = _sma(closes, 10), _sma(closes, 30), _sma(closes, 20)
    sd20 = _rolling_std(closes, 20)
    bb_pct = []
    for i in range(len(closes)):
        if sma20[i] is None or not sd20[i]:
            bb_pct.append(None)
        else:
            lower, upper = sma20[i] - 2 * sd20[i], sma20[i] + 2 * sd20[i]
            bb_pct.append((closes[i] - lower) / (upper - lower))
    r20 = [closes[i] / closes[i - 20] - 1 if i >= 20 else None for i in range(len(closes))]
    avg20v = _sma(vols, 20)
    # volume ratio compares today's volume with the average of the PREVIOUS 20 sessions
    vol_ratio = [vols[i] / avg20v[i - 1] if i >= 20 and avg20v[i - 1] else None for i in range(len(closes))]
    peak, dd, run_peak = [], [], 0.0
    for c in closes:
        run_peak = max(run_peak, c)
        peak.append(run_peak)
        dd.append(c / run_peak - 1 if run_peak else 0.0)
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(macd, 9)
    rets = [0.0] + [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    sd_r = _rolling_std(rets, 20)
    vol20 = [None if s is None else s * math.sqrt(bars_per_year) for s in sd_r]
    return {
        "sma10": sma10, "sma30": sma30, "bb_pct": bb_pct, "r20": r20, "vol_ratio": vol_ratio,
        "peak": peak, "dd": dd, "rsi14": _rsi(closes), "macd": macd, "macd_signal": signal,
        "macd_hist": [m - s for m, s in zip(macd, signal)], "atr14": _atr(highs, lows, closes),
        "vol20": vol20, "returns": rets,
    }


# --------------------------------------------------------------------------- models
def model_votes(candles, ind, i: int) -> Dict[str, Dict[str, Any]]:
    """Votes for session i using only data up to and including bar i."""
    c = candles[i]
    out: Dict[str, Dict[str, Any]] = {}

    s10, s30 = ind["sma10"][i], ind["sma30"][i]
    if s10 is None or s30 is None:
        out["trend"] = {"vote": 0, "input": None, "note": "warming up"}
    else:
        spread = s10 / s30 - 1
        out["trend"] = {"vote": 1 if s10 > s30 else -1, "input": spread,
                        "note": f"SMA10{'>' if s10 > s30 else '<'}SMA30 spread {spread:+.2%}"}

    r = ind["r20"][i]
    if r is None:
        out["momentum"] = {"vote": 0, "input": None, "note": "warming up"}
    else:
        vote = 1 if r > MOMENTUM_BAND else -1 if r < -MOMENTUM_BAND else 0
        where = "above +3%" if vote > 0 else "below -3%" if vote < 0 else "inside ±3%"
        out["momentum"] = {"vote": vote, "input": r, "note": f"20d return {r:+.2%} {where}"}

    vr = ind["vol_ratio"][i]
    if vr is None:
        out["volume"] = {"vote": 0, "input": None, "note": "warming up"}
    else:
        green = c["close"] >= c["open"]
        vote = (1 if green else -1) if vr > VOLUME_SPIKE else 0
        note = (f"volume spike {vr:.2f}x avg20 · {'green' if green else 'red'} candle" if vote
                else f"volume {vr:.2f}x avg20 · spike needs >{VOLUME_SPIKE:.2f}x")
        out["volume"] = {"vote": vote, "input": vr, "note": note}

    dd = ind["dd"][i]
    if dd < DD_LOW:
        vote, where = -1, "below -25%"
    elif dd <= DD_HIGH:
        vote, where = 1, "inside -25%..-5%"
    else:
        vote, where = 0, "above -5%"
    out["drawdown"] = {"vote": vote, "input": dd, "note": f"drawdown {dd:+.2%} {where}"}
    return out


def pm_decision(votes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    score = sum(WEIGHTS[k] * v["vote"] for k, v in votes.items())
    bull = sum(WEIGHTS[k] for k, v in votes.items() if v["vote"] > 0)
    bear = sum(WEIGHTS[k] for k, v in votes.items() if v["vote"] < 0)
    action = "BUY" if score >= BUY_SCORE else "SELL" if score <= SELL_SCORE else "HOLD"
    return {"action": action, "score": round(score, 2), "bull": round(bull, 2), "bear": round(bear, 2),
            "bull_pct": round(50 + 50 * score / MAX_SCORE, 1)}


# --------------------------------------------------------------------------- significance
def significance(votes: Sequence[int], fwd: Sequence[float], trials: int = 1000, seed: int = 7) -> Optional[float]:
    """Permutation test (idea from Jesse's rule-significance testing).

    Edge = mean of vote x forward return over the sessions where the model voted. The null keeps
    the model's exact vote counts but assigns them to random sessions (shuffles the vote vector
    against the real forward returns) `trials` times. p = share of random runs whose edge is at
    least the real one (+1 smoothing). Small p -> the rule's timing beats chance on this history.
    """
    import numpy as np

    v = np.asarray(votes, dtype=float)
    r = np.asarray(fwd, dtype=float)
    active = v != 0
    if active.sum() < 10 or len(v) < 20:
        return None
    actual = float((v * r)[active].mean())
    rng = np.random.default_rng(seed)
    perms = np.stack([rng.permutation(v) for _ in range(trials)])
    edges = (perms * r).sum(axis=1) / active.sum()
    return float((np.sum(edges >= actual) + 1) / (trials + 1))


# --------------------------------------------------------------------------- desk
def _max_drawdown(curve: Sequence[float]) -> float:
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def _sharpe(curve: Sequence[float], bars_per_year: float = BARS_PER_YEAR) -> float:
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))]
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return 0.0 if sd == 0 else m / sd * math.sqrt(bars_per_year)


def build_desk(candles: Sequence[Dict[str, float]], symbol: str = "BTCUSDT", fee_bps: float = 10.0,
               window: int = 365, bar_forming: bool = False, interval: str = "1d") -> Dict[str, Any]:
    """Run the whole desk over `candles` (oldest first, daily)."""
    n = len(candles)
    if n < MIN_BARS:
        return {"status": "INSUFFICIENT_DATA", "symbol": symbol, "bars": n, "required": MIN_BARS}
    for c in candles:
        if not all(math.isfinite(c[k]) and c[k] > 0 for k in ("open", "high", "low", "close")) or c["volume"] < 0:
            return {"status": "INVALID_DATA", "symbol": symbol, "bars": n}

    if interval not in INTERVALS:
        raise ValueError("Unsupported interval")
    bars_per_year = YEAR_SECONDS / INTERVALS[interval]
    ind = indicators(candles, bars_per_year)
    fee = fee_bps / 10000.0
    # The still-forming bar is displayed but never used for decisions.
    last_closed = n - 2 if bar_forming else n - 1
    start = max(30, last_closed - window + 1)

    sessions: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    equity = bh = 1.0
    eq_curve, bh_curve = [], []
    position: Optional[Dict[str, Any]] = None
    pending: Optional[str] = None  # action decided on the previous close
    fills = 0
    bars_in_market = 0
    prev_action = None

    for i in range(start, n):
        c = candles[i]
        prev_close = candles[i - 1]["close"]
        # 1) execute the previous session's decision at this bar's open
        day_ret = 0.0
        if pending == "BUY" and position is None:
            position = {"entry_time": c["open_time"], "entry": c["open"], "bars": 0}
            day_ret = (c["close"] / c["open"]) * (1 - fee) - 1
            fills += 1
        elif pending == "SELL" and position is not None:
            day_ret = (c["open"] / prev_close) * (1 - fee) - 1
            gross = c["open"] / position["entry"] - 1
            trades.append({"side": "LONG", "entry_time": position["entry_time"], "entry": position["entry"],
                           "exit_time": c["open_time"], "exit": c["open"], "sessions": position["bars"],
                           "gross_pct": gross, "net_pct": (1 + gross) * (1 - fee) ** 2 - 1})
            position = None
            fills += 1
        elif position is not None:
            day_ret = c["close"] / prev_close - 1
        if position is not None:
            position["bars"] += 1
            bars_in_market += 1
        if i > start:
            equity *= 1 + day_ret
            bh *= c["close"] / prev_close
        eq_curve.append(equity)
        bh_curve.append(bh)
        pending = None

        # 2) decide on this bar's close (skip the forming bar)
        if i > last_closed:
            continue
        votes = model_votes(candles, ind, i)
        pm = pm_decision(votes)
        holding = position is not None
        if pm["action"] == "BUY" and not holding:
            pending, execution = "BUY", "buys at next open"
        elif pm["action"] == "SELL" and holding:
            pending, execution = "SELL", "sells at next open"
        else:
            execution = "holds long" if holding else "stays flat"
        upnl = c["close"] / position["entry"] - 1 if position else None
        sessions.append({
            "i": i, "time": c["open_time"], "close": c["close"], "chg": c["close"] / prev_close - 1,
            "volume": c["volume"], "vol_ratio": ind["vol_ratio"][i],
            "votes": {k: v["vote"] for k, v in votes.items()},
            "notes": {k: v["note"] for k, v in votes.items()},
            "inputs": {k: v["input"] for k, v in votes.items()},
            "pm": pm, "prev_action": prev_action, "execution": execution, "upnl": upnl,
        })
        prev_action = pm["action"]

    # ----- scoreboard: each vote scored against the next SCORE_HORIZON sessions
    closes = [c["close"] for c in candles]
    scoreboard = []
    rows = [("pm", "PM", None, f"score vs ±{BUY_SCORE:.2f}")] + [(k, lbl, w, rule) for k, lbl, w, rule in MODELS]
    for key, label, weight, rule in rows:
        hits = scored = 0
        edge = 0.0
        votes_all, fwd_all = [], []
        for s in sessions:
            j = s["i"] + SCORE_HORIZON
            if j > last_closed:
                continue
            vote = ({"BUY": 1, "SELL": -1}.get(s["pm"]["action"], 0) if key == "pm" else s["votes"][key])
            fwd = closes[j] / closes[s["i"]] - 1
            votes_all.append(vote)
            fwd_all.append(fwd)
            if vote == 0:
                continue
            scored += 1
            hits += 1 if fwd * vote > 0 else 0
            edge += fwd * vote
        p_value = significance(votes_all, fwd_all)
        last = sessions[-1]
        scoreboard.append({
            "key": key, "label": label, "weight": weight, "rule": rule,
            "vote": ({"BUY": 1, "SELL": -1}.get(last["pm"]["action"], 0) if key == "pm" else last["votes"][key]),
            "input": last["pm"]["score"] if key == "pm" else last["inputs"][key],
            "n": scored, "hit_rate": hits / scored if scored else None,
            "edge": edge / scored if scored else None,
            "p_value": p_value,
            # Bonferroni: 5 rules are tested on the same history, so each must clear 0.05 / 5.
            "significant": p_value is not None and p_value < 0.05 / len(rows),
        })

    last = sessions[-1]
    lc = candles[last_closed]
    cur = candles[-1]
    open_pos = None
    if position is not None:
        open_pos = {"side": "LONG", "size": 1.0, "entry_time": position["entry_time"], "entry": position["entry"],
                    "sessions": position["bars"], "mark": cur["close"], "upnl": cur["close"] / position["entry"] - 1}
    closed_net = [t["net_pct"] for t in trades]
    rets_window = [ind["returns"][k] for k in range(start + 1, last_closed + 1)]
    sorted_rets = sorted(rets_window)
    var95 = sorted_rets[max(0, int(0.05 * len(sorted_rets)) - 1)] if sorted_rets else 0.0

    def pick(name, i):
        v = ind[name][i]
        return None if v is None else float(v)

    return {
        "status": "OK", "symbol": symbol, "interval": interval, "interval_seconds": INTERVALS[interval], "bars": n, "fee_bps": fee_bps,
        "bar_forming": bar_forming, "as_of": cur["open_time"], "decision_time": lc["open_time"],
        "models": [{"key": k, "label": lbl, "weight": w, "rule": rule} for k, lbl, w, rule in MODELS],
        "thresholds": {"buy": BUY_SCORE, "sell": SELL_SCORE, "max_score": MAX_SCORE},
        "ticker": {"open": cur["open"], "high": cur["high"], "low": cur["low"], "close": cur["close"],
                   "chg": cur["close"] / candles[-2]["close"] - 1, "abs_chg": cur["close"] - candles[-2]["close"],
                   "sma10": pick("sma10", n - 1), "sma30": pick("sma30", n - 1), "bb_pct": pick("bb_pct", n - 1),
                   "r20": pick("r20", n - 1), "vol_ratio": pick("vol_ratio", n - 1), "peak": ind["peak"][-1],
                   "dd": ind["dd"][-1], "rsi14": pick("rsi14", n - 1), "macd": ind["macd"][-1],
                   "macd_signal": ind["macd_signal"][-1], "macd_hist": ind["macd_hist"][-1]},
        "chart": {
            "candles": [{"time": int(c["open_time"]), "open": c["open"], "high": c["high"], "low": c["low"],
                         "close": c["close"], "volume": c["volume"]} for c in candles[start:]],
            "sma10": ind["sma10"][start:], "sma30": ind["sma30"][start:], "rsi14": ind["rsi14"][start:],
            "macd": ind["macd"][start:], "macd_signal": ind["macd_signal"][start:],
            "macd_hist": ind["macd_hist"][start:], "vol_ratio": ind["vol_ratio"][start:],
        },
        "decision": {**last["pm"], "prev_action": last["prev_action"], "execution": last["execution"],
                     "votes": last["votes"], "notes": last["notes"], "inputs": last["inputs"]},
        "risk": {"atr14": pick("atr14", last_closed), "vol20": pick("vol20", last_closed),
                 "var95_1d": var95, "worst_day": min(rets_window) if rets_window else 0.0},
        "votes": [{"time": s["time"], **s["votes"], "bull_pct": s["pm"]["bull_pct"], "action": s["pm"]["action"]}
                  for s in sessions[-90:]],
        "equity": {"times": [int(c["open_time"]) for c in candles[start:]], "agents": eq_curve, "buy_hold": bh_curve,
                   "agents_return": eq_curve[-1] - 1, "buy_hold_return": bh_curve[-1] - 1,
                   "edge_pts": (eq_curve[-1] - bh_curve[-1]) * 100, "max_dd": _max_drawdown(eq_curve),
                   "buy_hold_max_dd": _max_drawdown(bh_curve), "sharpe": _sharpe(eq_curve, bars_per_year),
                   "since": int(candles[start]["open_time"])},
        "position": open_pos,
        "trades": trades[-8:],
        "all_trades": trades,
        "book": {"closed": len(trades), "won": sum(1 for x in closed_net if x > 0),
                 "avg_net": sum(closed_net) / len(closed_net) if closed_net else None,
                 "exposure": bars_in_market / max(1, len(eq_curve)), "fills": fills},
        "scoreboard": scoreboard,
        "transcript": sessions[-12:],
    }
