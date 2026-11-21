"""Statistical jump model for market regimes (Nystrup et al.; Shu, Yu & Mulvey 2024 found it beat HMM-guided
allocation out of sample, net of costs, on equity indices). Like k-means on return features, plus a penalty
`lam` for every state switch, so regimes are persistent and turnover stays low.

Fit (2 states, coordinate descent):
  states  = argmin_s  sum_t ||x_t - theta_{s_t}||^2 + lam * sum_t 1[s_t != s_{t-1}]   (Viterbi-style DP)
  theta_k = mean of x_t assigned to k
Features: rolling mean return and rolling volatility (standardised). The bull state is the one with the
higher mean return. For trading, the state at bar t comes from a fit on bars <= t only (refit every
`refit` bars), and the last decoded state is used (no smoothing with future bars).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np


def _raw_features(close: Sequence[float], w: int = 10) -> np.ndarray:
    """Rolling mean log return and rolling volatility, one row per bar after the first (unscaled)."""
    r = np.diff(np.log(np.asarray(close, float)))
    m = np.array([r[max(0, i - w + 1):i + 1].mean() for i in range(len(r))])
    v = np.array([r[max(0, i - w + 1):i + 1].std() for i in range(len(r))])
    return np.c_[m, v]


def decode(X: np.ndarray, theta: np.ndarray, lam: float) -> np.ndarray:
    """Most likely state path for fixed centroids: min sum ||x_t - theta_s||^2 + lam * #switches (Viterbi)."""
    k = len(theta)
    cost = ((X[:, None, :] - theta[None, :, :]) ** 2).sum(-1)              # T x k
    dp, back = cost[0].copy(), np.zeros((len(X), k), int)
    for t in range(1, len(X)):
        trans = dp[:, None] + lam * (1 - np.eye(k))                          # prev x next
        back[t] = trans.argmin(0)
        dp = trans.min(0) + cost[t]
    states = np.zeros(len(X), int)
    states[-1] = int(dp.argmin())
    for t in range(len(X) - 1, 0, -1):
        states[t - 1] = back[t, states[t]]
    return states


def fit_jump_model(X: np.ndarray, lam: float = 50.0, k: int = 2, iters: int = 20, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    theta = X[rng.choice(len(X), k, replace=False)]
    states = np.zeros(len(X), int)
    for _ in range(iters):
        new = decode(X, theta, lam)
        if (new == states).all():
            break
        states = new
        for j in range(k):
            if (states == j).any():
                theta[j] = X[states == j].mean(0)
    return states, theta


def online_bull_states(close: Sequence[float], lam: float = 50.0, refit: int = 20, warmup: int = 150, decode_window: int = 60,
                       w: int = 10) -> List[Optional[int]]:
    """1 = bull, 0 = bear, None before warm-up. State at t uses closes[0..t] only."""
    n = len(close)
    out: List[Optional[int]] = [None] * n
    theta = mu = sd = None
    bull = 0
    for t in range(warmup, n):
        if (t - warmup) % refit == 0:
            raw = _raw_features(close[: t + 1], w)
            mu, sd = raw.mean(0), raw.std(0) + 1e-12                         # scaling fixed at fit time
            states, theta = fit_jump_model((raw - mu) / sd, lam)
            bull = int(np.argmax(theta[:, 0]))                                # higher mean-return centroid
            out[t] = int(states[-1] == bull)
            continue
        # Between refits: decode a trailing window with the fitted centroids. The last state of that path
        # uses bars <= t only, and evidence can accumulate over several bars to pay the switching penalty.
        win = (_raw_features(close[max(0, t - decode_window - w): t + 1], w)[-decode_window:] - mu) / sd
        out[t] = int(decode(win, theta, lam)[-1] == bull)
    return out
