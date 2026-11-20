"""Out-of-sample validation for strategy candidates (Lopez de Prado; Bailey, Borwein, Lopez de Prado & Zhu).

Three tools, used together by the Strategy Lab's promotion gate:

Triple-barrier labels
    Each entry is held until the first of three barriers: the take-profit (upper), the stop-loss
    (lower) or the time limit (vertical). The barriers come from the bot's own bracket, so a label is
    exactly the trade the bot would have taken. Bars are the only resolution available, so when one
    bar touches both the target and the stop, the stop is assumed to have come first (conservative).
    A gap through a barrier fills at that bar's open, never at the better barrier price.

CPCV (combinatorial purged cross-validation)
    The timeline is cut into N contiguous groups; every choice of k groups is a test set and the rest
    is the training set, giving C(N, k) splits. Training observations whose label window overlaps a
    test group are purged, and an embargo of `embargo` observations after each test group is dropped
    too, so no information leaks from test labels into training.

PBO (probability of backtest overfitting, Bailey et al. 2017, CSCV)
    For each split, pick the candidate with the best in-sample Sharpe and find its relative rank
    omega among all candidates out of sample. lambda = ln(omega / (1 - omega)). PBO is the share of
    splits with lambda <= 0, i.e. how often the in-sample winner lands at or below the out-of-sample
    median. With no real edge PBO is about 0.5; a genuine edge pushes it towards 0.

The Deflated Sharpe Ratio is reused from core.quant.levels.level10_research.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.quant.levels.level10_research import compute_deflated_sharpe_ratio

UPPER, LOWER, VERTICAL = 1, -1, 0


# --------------------------------------------------------------------------- triple barrier
def triple_barrier_labels(
    open_: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    signals: Sequence[int],
    stop_pct: Sequence[float],
    target_pct: Sequence[float],
    horizon_bars: int,
    fee: float = 0.001,
    one_at_a_time: bool = True,
) -> List[Dict[str, float]]:
    """Label every signal bar t (decided on t's close) as a bracket trade entered at bar t+1's open.

    stop_pct / target_pct are per-bar fractions of entry (from the signal bar's ATR). `fee` is charged
    per side on the notional, so a round trip costs about 2 * fee. With one_at_a_time, a signal that
    arrives while the previous trade is still open is skipped, as the bot holds one position per coin.
    Returns dicts: signal, entry, exit (bar indices), entry_price, exit_price, barrier, ret (net).
    """
    n = len(close)
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    trades: List[Dict[str, float]] = []
    busy_until = -1
    for t in range(n - 1):
        if not signals[t] or (one_at_a_time and t < busy_until):
            continue
        e = t + 1
        entry = float(open_[e])
        if entry <= 0:
            continue
        stop_px = entry * (1 - float(stop_pct[t]))
        target_px = entry * (1 + float(target_pct[t]))
        last = min(n - 1, e + horizon_bars - 1)
        barrier, exit_px, x = VERTICAL, float(close[last]), last
        for j in range(e, last + 1):
            if j > e and open_[j] <= stop_px:            # gapped through the stop: fill at the open
                barrier, exit_px, x = LOWER, float(open_[j]), j
                break
            if j > e and open_[j] >= target_px:          # gapped through the target: fill at the target
                barrier, exit_px, x = UPPER, target_px, j
                break
            if low[j] <= stop_px:                        # both touched in one bar: stop first
                barrier, exit_px, x = LOWER, stop_px, j
                break
            if high[j] >= target_px:
                barrier, exit_px, x = UPPER, target_px, j
                break
        if barrier == VERTICAL and e + horizon_bars - 1 > n - 1:
            break                                        # time barrier lies beyond the data: unlabelled
        trades.append({"signal": t, "entry": e, "exit": x, "entry_price": entry, "exit_price": exit_px,
                       "barrier": barrier, "ret": (exit_px / entry) * (1 - fee) ** 2 - 1})
        busy_until = x                                   # a new signal may come on the exit bar's close
    return trades


# --------------------------------------------------------------------------- CPCV
def group_bounds(n_obs: int, n_groups: int) -> List[Tuple[int, int]]:
    """Contiguous [start, end) groups covering 0..n_obs-1 as evenly as possible."""
    if n_groups < 2 or n_obs < n_groups:
        raise ValueError("need n_obs >= n_groups >= 2")
    edges = np.linspace(0, n_obs, n_groups + 1).round().astype(int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(n_groups)]


def cpcv_splits(
    n_obs: int,
    n_groups: int = 6,
    n_test_groups: int = 2,
    label_end: Optional[Sequence[int]] = None,
    embargo: int = 0,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """All C(n_groups, n_test_groups) purged and embargoed (train_idx, test_idx) splits.

    label_end[i] is the last observation index that observation i's label depends on (its exit bar);
    by default every label ends where it starts. A training observation is purged when its label
    window [i, label_end[i]] overlaps a test group, and observations within `embargo` after the end
    of each test group are embargoed.
    """
    if not 1 <= n_test_groups < n_groups:
        raise ValueError("need 1 <= n_test_groups < n_groups")
    ends = np.arange(n_obs) if label_end is None else np.maximum(np.asarray(label_end, dtype=int), np.arange(n_obs))
    starts = np.arange(n_obs)
    bounds = group_bounds(n_obs, n_groups)
    splits = []
    for test in combinations(range(n_groups), n_test_groups):
        is_test = np.zeros(n_obs, dtype=bool)
        keep = np.ones(n_obs, dtype=bool)
        for g in test:
            a, b = bounds[g]
            is_test[a:b] = True
            keep &= ~((starts < b) & (ends >= a))          # purge: label window touches the test group
            keep[b:min(n_obs, b + embargo)] = False         # embargo right after the test group
        train = np.flatnonzero(keep & ~is_test)
        splits.append((train, np.flatnonzero(is_test)))
    return splits


# --------------------------------------------------------------------------- PBO
def _sharpe_cols(m: np.ndarray) -> np.ndarray:
    if m.shape[0] < 2:
        return np.zeros(m.shape[1])
    mu, sd = m.mean(axis=0), m.std(axis=0, ddof=1)
    return np.divide(mu, sd, out=np.zeros_like(mu), where=sd > 1e-12)


def probability_of_backtest_overfitting(
    returns: np.ndarray,
    n_groups: int = 10,
    label_end: Optional[Sequence[int]] = None,
    embargo: int = 0,
    splits: Optional[List[Tuple[np.ndarray, np.ndarray]]] = None,
) -> Dict[str, object]:
    """PBO of choosing the best in-sample column of `returns` (T observations x N candidates).

    Default splits are CSCV: every half of `n_groups` groups is in-sample once (C(n_groups, n_groups/2)),
    with CPCV purging and embargo applied to the in-sample half. Columns are scored by Sharpe.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2 or r.shape[1] < 2:
        raise ValueError("returns must be T x N with N >= 2 candidates")
    t, n = r.shape
    if splits is None:
        splits = cpcv_splits(t, n_groups, n_groups // 2, label_end, embargo)
    logits, degradation = [], []
    for train, test in splits:
        if len(train) < 2 or len(test) < 2:
            continue
        is_sr, oos_sr = _sharpe_cols(r[train]), _sharpe_cols(r[test])
        best = int(np.argmax(is_sr))
        # relative rank of the IS winner OOS, ties averaged; omega in (0, 1)
        rank = (oos_sr < oos_sr[best]).sum() + 0.5 * ((oos_sr == oos_sr[best]).sum() - 1) + 1
        omega = rank / (n + 1)
        logits.append(math.log(omega / (1 - omega)))
        degradation.append((float(is_sr[best]), float(oos_sr[best])))
    if not logits:
        return {"pbo": None, "splits": 0, "logits": [], "is_vs_oos": []}
    lam = np.asarray(logits)
    return {"pbo": float((lam <= 0).mean()), "splits": len(lam), "logits": lam.tolist(),
            "is_vs_oos": degradation}


# --------------------------------------------------------------------------- DSR
def deflated_sharpe(trade_returns: Sequence[float], n_trials: int, var_sharpe: Optional[float] = None) -> Dict[str, float]:
    """Per-trade Sharpe and its Deflated Sharpe probability; p = 1 - DSR (H0: the best of n_trials is luck).

    var_sharpe is the variance of the per-trade Sharpe across all candidates tried; when unknown
    (fewer than two candidates) the null's sampling variance 1/T is used.
    """
    x = np.asarray(trade_returns, dtype=float)
    if len(x) < 4 or float(np.std(x, ddof=1)) < 1e-12:
        return {"sharpe": 0.0, "dsr": 0.0, "p_value": 1.0}
    sr = float(np.mean(x) / np.std(x, ddof=1))
    v = var_sharpe if var_sharpe and var_sharpe > 0 else 1.0 / len(x)
    dsr = compute_deflated_sharpe_ratio(sr if sr != 0 else 1e-12, returns=x, n_trials=max(1, int(n_trials)), var_sharpe=v)
    return {"sharpe": sr, "dsr": float(dsr), "p_value": float(1.0 - dsr)}
