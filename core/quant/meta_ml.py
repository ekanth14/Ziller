"""Meta-labeling with gradient boosting (Lopez de Prado, AFML ch. 3): does a model, trained only on the past,
pick out which of a strategy's trades are worth taking?

Pipeline (no lookahead):
1. Primary signals: entry bars of a Lab strategy (flat -> long).
2. Labels: each signal replayed as the bot's own bracket trade (triple barrier: target / stop / time) with fees.
3. Features at the signal bar only: 1/5/20-bar returns, ATR%, RSI(14), volatility ratio (10 vs 60 bars),
   volume z-score (20), distance to SMA50 and to the 20-bar high.
4. Walk-forward: train on trades that EXITED before the test block starts (purging), skip an embargo of
   `embargo` signals, predict the next block; repeat. Model: LightGBM when available (small, regularised),
   else a numpy logistic regression.
5. Compare out-of-sample: all primary trades vs trades the model would take (P(win) >= threshold).

The verdict is honest: if filtered trades do not have better net expectancy, the filter adds nothing.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

FEATURES = ("ret1", "ret5", "ret20", "atr_pct", "rsi14", "vol_ratio", "volume_z", "dist_sma50", "dist_high20")


def _features(c: Sequence[Dict[str, float]], t: int) -> Optional[List[float]]:
    if t < 61:
        return None
    cl = [b["close"] for b in c[: t + 1]]
    hi = [b["high"] for b in c[: t + 1]]
    lo = [b["low"] for b in c[: t + 1]]
    vol = [b.get("volume", 0.0) for b in c[: t + 1]]
    r = [cl[i] / cl[i - 1] - 1 for i in range(1, len(cl))]
    tr = [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(len(cl) - 14, len(cl))]
    g = [max(0.0, x) for x in r[-14:]]
    ls = [max(0.0, -x) for x in r[-14:]]
    rsi = 100.0 if sum(ls) == 0 else 100 - 100 / (1 + sum(g) / sum(ls))

    def sd(xs):
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))
    v20 = vol[-20:]
    vz = (vol[-1] - sum(v20) / 20) / (sd(v20) or 1.0)
    s50 = sum(cl[-50:]) / 50
    return [cl[-1] / cl[-2] - 1, cl[-1] / cl[-6] - 1, cl[-1] / cl[-21] - 1, (sum(tr) / 14) / cl[-1], rsi / 100,
            (sd(r[-10:]) / (sd(r[-60:]) or 1e-12)), vz, cl[-1] / s50 - 1, cl[-1] / max(hi[-20:]) - 1]


def _fit_predict(X_tr, y_tr, X_te):
    if len(set(y_tr)) < 2:
        return np.full(len(X_te), float(np.mean(y_tr))), "constant"
    try:
        import lightgbm as lgb
        m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=7, min_child_samples=10,
                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)
        m.fit(np.asarray(X_tr), np.asarray(y_tr))
        return m.predict_proba(np.asarray(X_te))[:, 1], "lightgbm"
    except Exception:
        pass
    X = np.asarray(X_tr, float)
    mu, sdv = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sdv]
    w = np.zeros(Z.shape[1])
    y = np.asarray(y_tr, float)
    for _ in range(500):                       # L2-regularised logistic regression by gradient descent
        p = 1 / (1 + np.exp(-Z @ w))
        w -= 0.1 * (Z.T @ (p - y) / len(y) + 0.01 * np.r_[0, w[1:]])
    Zt = np.c_[np.ones(len(X_te)), (np.asarray(X_te, float) - mu) / sdv]
    return 1 / (1 + np.exp(-Zt @ w)), "logistic"


def evaluate_meta_label(c: Sequence[Dict[str, float]], positions: Sequence[int], stop_pct: float, target_pct: float,
                        horizon_bars: int, fee: float = 0.001, n_blocks: int = 5, embargo: int = 2,
                        threshold: float = 0.5, min_train: int = 30) -> Dict[str, Any]:
    from core.quant.validation import triple_barrier_labels
    n = len(c)
    signals = [1 if i > 0 and positions[i] and not positions[i - 1] else 0 for i in range(n)]
    trades = triple_barrier_labels([b["open"] for b in c], [b["high"] for b in c], [b["low"] for b in c],
                                   [b["close"] for b in c], signals, [stop_pct] * n, [target_pct] * n,
                                   horizon_bars, fee=fee)
    rows = []
    for tr in trades:
        f = _features(c, int(tr["signal"]))
        if f is not None and all(math.isfinite(x) for x in f):
            rows.append((tr, f))
    if len(rows) < min_train + 10:
        return {"status": "INSUFFICIENT_DATA", "trades": len(rows), "needed": min_train + 10}
    # walk-forward blocks over the later part of the sample; first block is training-only
    size = max(5, len(rows) // (n_blocks + 1))
    oos, model_used = [], None
    for b in range(1, n_blocks + 1):
        lo, hi = b * size, (b + 1) * size if b < n_blocks else len(rows)
        if lo >= len(rows):
            break
        start_bar = rows[lo][0]["signal"]
        train = [(t, f) for t, f in rows[: max(0, lo - embargo)] if t["exit"] < start_bar]   # purge overlaps
        if len(train) < min_train:
            continue
        p, model_used = _fit_predict([f for _, f in train], [1 if t["ret"] > 0 else 0 for t, _ in train],
                                     [f for _, f in rows[lo:hi]])
        oos += [(t, float(pi)) for (t, _), pi in zip(rows[lo:hi], p)]
    if not oos:
        return {"status": "INSUFFICIENT_DATA", "trades": len(rows), "needed": min_train + 10}

    def summary(ts):
        rets = [t["ret"] for t in ts]
        return {"trades": len(rets), "win_rate": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
                "expectancy": (sum(rets) / len(rets)) if rets else None, "total": sum(rets)}
    all_t = summary([t for t, _ in oos])
    taken = summary([t for t, p in oos if p >= threshold])
    skipped = summary([t for t, p in oos if p < threshold])
    y = np.array([1 if t["ret"] > 0 else 0 for t, _ in oos])
    pr = np.array([p for _, p in oos])
    auc = None
    if 0 < y.sum() < len(y):                      # rank-based AUC (Mann-Whitney)
        order = pr.argsort()
        ranks = np.empty(len(pr))
        ranks[order] = np.arange(1, len(pr) + 1)
        auc = float((ranks[y == 1].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (len(y) - y.sum())))
    helps = (taken["expectancy"] is not None and all_t["expectancy"] is not None and taken["trades"] >= 20
             and taken["expectancy"] > all_t["expectancy"] and taken["expectancy"] > 0)
    return {"status": "OK", "model": model_used, "features": list(FEATURES), "threshold": threshold,
            "oos_all": all_t, "oos_taken": taken, "oos_skipped": skipped, "auc": auc,
            "verdict": ("Filter improves out-of-sample expectancy and is net positive." if helps else
                        "Filter does not produce positive, better out-of-sample expectancy: do not use it.")}
