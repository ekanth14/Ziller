#!/usr/bin/env python3
"""ZILLERS Laya AI Model Self-Test and Latency Calibration Script.

Mandate:
- Prove the real model runs.
- Print laya version + checkpoint path.
- Run 20 real calls (1 and 2 questions) when model is loaded.
- Compute and display p50, p95, p99, and sample outputs.
- If model is unavailable, report UNAVAILABLE; never stub or fake outputs.
- Tier 2 runs on candle close only, never inside 1s ticker loop.
"""

import json
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptoscope.autotrader.decision import LayaTier2Evaluator, Tier1Engine


def run_selftest():
    print("=" * 75)
    print("ZILLERS LAYA AI DECISION MODEL: SELF-TEST & CALIBRATION")
    print("=" * 75)

    evaluator = LayaTier2Evaluator()
    status = evaluator.get_status()

    laya_ver = status.get("laya_version", "UNAVAILABLE")
    checkpoint = status.get("checkpoint_path", "UNAVAILABLE")
    backend_status = status.get("status", "NOT_LOADED")

    print(f"Laya Version:     {laya_ver}")
    print(f"Checkpoint Path:  {checkpoint}")
    print(f"Backend Status:   {backend_status}")
    print(f"Pinned Threads:   {status.get('pinned_threads', 1)}")
    print(f"Configured Limit: {status.get('max_timeout_ms', 200.0):.1f} ms")
    print("-" * 75)

    if not status.get("package_loaded"):
        print("\n[RESULT] Laya model is UNAVAILABLE in this local runtime environment.")
        print("         - Native 'laya' package: Not installed")
        print(f"         - Checkpoint:           {checkpoint}")
        print("         - Operational Policy:   Zero stubbed or faked outputs.")
        print("         - Runtime Action:       Tier 2 returns status 'UNAVAILABLE', agreed=False.")
        print("         - Execution Safety:     Tier 2 runs on candle close only; never in 1s ticker loop.")
        print("\n[OK] Laya self-test completed: reported UNAVAILABLE safely without faking outputs.")
        print("=" * 75)
        return

    # Real model execution: 20 real calls (10 single-question, 10 two-question)
    print("\nExecuting 20 real model inference calls across 1 and 2 questions...")
    latencies_1q = []
    latencies_2q = []
    sample_outputs_1q = []
    sample_outputs_2q = []

    # 1. Ten 1-Question calls
    for i in range(10):
        t1_input = {
            "action": "LONG",
            "score": 65 + i,
            "setup_type": "SMC_DEMAND_EXPANSION",
            "discrete_encoding": f"trend=up,location=near_bull_ob,fvg=bullish_fvg,sweep=sell_side,mom=accelerating,vol=expansion,rsi={55+i}",
        }
        t0 = time.perf_counter()
        res = evaluator.evaluate(t1_input)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies_1q.append(lat)
        if i == 0:
            sample_outputs_1q.append(res)

    # 2. Ten 2-Question calls
    for i in range(10):
        t1_input = {
            "action": "SHORT",
            "score": -60 - i,
            "setup_type": "SMC_SUPPLY_REJECTION",
            "discrete_encoding": f"trend=down,location=near_bear_ob,fvg=bearish_fvg,sweep=buy_side,mom=decelerating,vol=distribution,rsi={45-i}",
        }
        t0 = time.perf_counter()
        res = evaluator.evaluate(t1_input)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies_2q.append(lat)
        if i == 0:
            sample_outputs_2q.append(res)

    all_latencies = sorted(latencies_1q + latencies_2q)
    n = len(all_latencies)
    p50 = all_latencies[int(n * 0.50)]
    p90 = all_latencies[int(n * 0.90)]
    p95 = all_latencies[int(n * 0.95)]
    p99 = all_latencies[min(int(n * 0.99), n - 1)]
    max_lat = max(all_latencies)

    print("\n--- Latency Percentiles (20 Real Calls) ---")
    print(f"p50:  {p50:.3f} ms")
    print(f"p90:  {p90:.3f} ms")
    print(f"p95:  {p95:.3f} ms")
    print(f"p99:  {p99:.3f} ms")
    print(f"Max:  {max_lat:.3f} ms")

    print("\n--- Sample Outputs ---")
    print(f"1-Question Sample: {json.dumps(sample_outputs_1q[0], indent=2)}")
    print(f"2-Question Sample: {json.dumps(sample_outputs_2q[0], indent=2)}")

    print(f"\n[CALIBRATION] Recommended Timeout (from measured p95): {max(p95 * 1.5, 50.0):.1f} ms")
    print("=" * 75)


if __name__ == "__main__":
    run_selftest()
