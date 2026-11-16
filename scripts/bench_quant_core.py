"""Baseline benchmark for the pure-Python quant core (run before any native port).

Usage:  python scripts/bench_quant_core.py [--bars 2000] [--json out.json] [--profile]

Measures per-call latency (p50/p95/p99, microseconds) for the hot paths identified in
the native-code plan, using deterministic synthetic data so runs are comparable.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import math
import pstats
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.quant.levels.level10_research import detect_regimes_hmm  # noqa: E402
from core.quant.pipeline import QuantPipeline  # noqa: E402
from core.quant.stage3_filter import compute_half_life, compute_hurst_exponent  # noqa: E402
from core.quant.stage8_validate import run_monte_carlo_drawdown  # noqa: E402


def synthetic_bars(n: int, seed: int = 7):
    rng = random.Random(seed)
    price = 100.0
    for _ in range(n):
        o = price
        price *= math.exp(rng.gauss(0.0, 0.01))
        h = max(o, price) * (1 + abs(rng.gauss(0, 0.002)))
        low = min(o, price) * (1 - abs(rng.gauss(0, 0.002)))
        yield o, h, low, price, rng.uniform(100, 1000)


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def summarize(samples_s):
    us = [s * 1e6 for s in samples_s]
    return {
        "n": len(us),
        "p50_us": round(statistics.median(us), 2),
        "p95_us": round(pct(us, 0.95), 2),
        "p99_us": round(pct(us, 0.99), 2),
        "max_us": round(max(us), 2),
    }


def timed(fn, repeat):
    out = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return out


def bench_on_bar(bars: int):
    """Per-bar latency as history grows: exposes the O(n) per-bar recompute."""
    pipe = QuantPipeline("BTCUSDT")
    lat = []
    for o, h, low, c, v in synthetic_bars(bars):
        t0 = time.perf_counter()
        pipe.on_bar(o, h, low, c, v, c * 0.9999, 1.0, c * 1.0001, 1.2, equity=10000.0)
        lat.append(time.perf_counter() - t0)
    third = max(1, bars // 3)
    return {
        "first_third": summarize(lat[:third]),
        "last_third": summarize(lat[-third:]),
        "total_s": round(sum(lat), 3),
        "growth_last_vs_first_p50": round(
            statistics.median(lat[-third:]) / max(statistics.median(lat[:third]), 1e-12), 1
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=2000)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--profile", action="store_true", help="cProfile the on_bar loop")
    args = ap.parse_args()

    closes = [b[3] for b in synthetic_bars(args.bars)]
    rng = random.Random(11)
    trades = [rng.gauss(0.002, 0.02) for _ in range(300)]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

    results = {
        "bars": args.bars,
        "on_bar": bench_on_bar(args.bars),
        "hurst_exponent": summarize(timed(lambda: compute_hurst_exponent(closes[-500:]), 200)),
        "half_life": summarize(timed(lambda: compute_half_life(closes[-500:]), 200)),
        "monte_carlo_drawdown_300_trades": summarize(
            timed(lambda: run_monte_carlo_drawdown(trades, iterations=1000, confidence=0.95), 10)
        ),
        "hmm_fit_500_returns": summarize(timed(lambda: detect_regimes_hmm(returns[:500], n_states=2), 3)),
    }
    print(json.dumps(results, indent=2))
    if args.json:
        args.json.write_text(json.dumps(results, indent=2))

    if args.profile:
        pr = cProfile.Profile()
        pr.enable()
        bench_on_bar(min(args.bars, 1000))
        pr.disable()
        pstats.Stats(pr).sort_stats("cumulative").print_stats(12)


if __name__ == "__main__":
    main()
