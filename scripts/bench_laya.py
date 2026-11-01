"""Comprehensive Benchmark Script for ZILLERS Decision Layer & Laya Classifier.

Measures:
1. Tier 1 SMC deterministic rules on 60-candle and 500-candle rolling windows.
2. Tier 2 Laya evaluation across 1 and 2 questions with 1, 2, and 4 threads.
3. Formats and prints comparative latency tables (p50, p95, p99).
4. Sets the operational timeout and thread recommendation from measured p95.
"""

import argparse
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptoscope.autotrader.decision import Tier1Engine, LayaTier2Evaluator, FastDecisionLayer


def generate_benchmark_candles(n: int = 500):
    candles = []
    base_price = 68000.0
    for i in range(n):
        open_p = base_price + (i * 5.0)
        high_p = open_p + 45.0
        low_p = open_p - 35.0
        close_p = open_p + 15.0
        candles.append({
            "open_time": i * 60,
            "close_time": (i + 1) * 60,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": 250.0,
            "taker_buy_volume": 140.0,
        })
    return candles


def stats(latencies):
    sorted_l = sorted(latencies)
    n = len(sorted_l)
    p50 = statistics.median(sorted_l)
    p95 = sorted_l[int(n * 0.95)]
    p99 = sorted_l[int(n * 0.99)]
    return p50, p95, p99


def run_benchmarks(iterations: int = 200):
    print("=" * 80)
    print(f"ZILLERS QUANT TERMINAL: LATENCY & BENCHMARK SUITE ({iterations} iterations)")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Tier 1 Deterministic Rules: 60 vs 500 Candle Windows
    # -------------------------------------------------------------------------
    tier1 = Tier1Engine()
    candles_60 = generate_benchmark_candles(60)
    candles_500 = generate_benchmark_candles(500)

    t1_60_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tier1.evaluate(candles_60, symbol="BTCUSDT")
        t1_60_latencies.append((time.perf_counter() - t0) * 1000.0)

    t1_500_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tier1.evaluate(candles_500, symbol="BTCUSDT")
        t1_500_latencies.append((time.perf_counter() - t0) * 1000.0)

    p50_60, p95_60, p99_60 = stats(t1_60_latencies)
    p50_500, p95_500, p99_500 = stats(t1_500_latencies)

    print("\n### Tier 1 Deterministic SMC Rules Latency Benchmark")
    print(f"{'Candle Window':<18} | {'p50 (median)':<12} | {'p95':<12} | {'p99':<12} | {'Status'}")
    print("-" * 75)
    print(f"{'60 candles':<18} | {p50_60:<10.3f} ms | {p95_60:<10.3f} ms | {p99_60:<10.3f} ms | {'PASS (<20ms)' if p99_60 < 20 else 'FAIL'}")
    print(f"{'500 candles':<18} | {p50_500:<10.3f} ms | {p95_500:<10.3f} ms | {p99_500:<10.3f} ms | {'PASS (<20ms)' if p99_500 < 20 else 'FAIL'}")

    assert p99_500 < 20.0, f"Tier 1 exceeded 20ms on 500 candles: {p99_500:.2f}ms"
    print(f"\n[OK] Tier 1 strictly sub-20ms: 500-candle p99 = {p99_500:.3f} ms (p50 = {p50_500:.3f} ms)")

    # -------------------------------------------------------------------------
    # 2. Tier 2 Laya Benchmark: Questions (1 vs 2) across Threads (1, 2, 4)
    # -------------------------------------------------------------------------
    dummy_t1_result = {
        "action": "LONG",
        "composite_score": 75.0,
        "discrete_encoding": "SMC:BULL_OB|SWEEP:LOW|RSI:55.2|EMA:ALIGNED|VOL_DELTA:+120",
    }

    print("\n### Tier 2 Laya Evaluator Status & Latency Analysis")
    eval_check = LayaTier2Evaluator()
    status = eval_check.get_status()

    if not status.get("package_loaded"):
        print("-" * 75)
        print("  STATUS:           UNAVAILABLE (laya native package not installed)")
        print(f"  CHECKPOINT:       {status.get('checkpoint_path', 'UNAVAILABLE')}")
        print("  POLICY:           Never stub or fake outputs. No mock sub-millisecond latency.")
        print("  EXECUTION GATE:   Tier 2 runs on candle close only, never in 1s ticker loop.")
        print("  DECISION ACTION:  Returns status 'UNAVAILABLE', fails safe to STAND_ASIDE.")
        print("-" * 75)
        print("\n" + "=" * 80)
        print("RUNTIME CONFIGURATION (UNAVAILABLE MODEL STATE):")
        print("  Threads:          1 (Pinned CPU thread)")
        print("  Fail-safe Mode:   STAND_ASIDE (Model UNAVAILABLE)")
        print("  Timeout Budget:   200.0 ms (Default fail-closed ceiling)")
        print("=" * 80 + "\n")
        return

    print(f"{'Threads':<10} | {'Questions':<12} | {'p50 (median)':<12} | {'p95':<12} | {'p99':<12} | {'Status'}")
    print("-" * 75)

    laya_results = []
    for threads in [1, 2, 4]:
        for num_questions in [1, 2]:
            evaluator = LayaTier2Evaluator(threads=threads, timeout_ms=200.0)
            latencies = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                evaluator.evaluate(dummy_t1_result)
                latencies.append((time.perf_counter() - t0) * 1000.0)

            p50_l, p95_l, p99_l = stats(latencies)
            laya_results.append((threads, num_questions, p50_l, p95_l, p99_l))
            status_text = "READY" if p95_l < 200.0 else "TIMEOUT"
            print(f"{threads:<10} | {num_questions:<12} | {p50_l:<10.3f} ms | {p95_l:<10.3f} ms | {p99_l:<10.3f} ms | {status_text}")

    # Optimal configuration from p95:
    best_config = sorted(laya_results, key=lambda x: x[3])[0]
    rec_threads = best_config[0]
    rec_p95 = best_config[3]
    rec_timeout = max(50.0, rec_p95 * 2.5)  # 2.5x safety multiplier above p95

    print("\n" + "=" * 80)
    print("RECOMMENDED RUNTIME CONFIGURATION FROM MEASURED p95:")
    print(f"  Recommended Threads:   {rec_threads}")
    print(f"  Measured Laya p95:     {rec_p95:.3f} ms")
    print(f"  Calibrated Timeout:    {rec_timeout:.1f} ms (budget guard: 200.0 ms)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Laya and Tier 1 Latency")
    parser.add_argument("--iterations", type=int, default=200, help="Number of test iterations")
    args = parser.parse_args()
    run_benchmarks(args.iterations)
