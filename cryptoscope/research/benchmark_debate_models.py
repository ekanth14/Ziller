"""Benchmark debate LLM candidates: laya-crypto:latest vs gemma4:12b.

Measures:
- Cold-start latency (1st prompt) vs Warm latency (subsequent prompts)
- p50 and p95 latency
- Valid JSON parsing rate
- Eval tokens count and tokens/second
- Consensus actions and conviction distribution
Logs full audit trail to work/reports/ollama_benchmark_results.csv.
"""

import csv
import json
import logging
import os
from pathlib import Path
import statistics
import time
from typing import Any, Dict, List, Tuple
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cryptoscope.benchmark")

BENCHMARK_PROMPTS = [
    {
        "id": "PROMPT_01_BTC_BULL_BREAKOUT",
        "symbol": "BTCUSDT",
        "direction": "BUY",
        "entry": 68500.0,
        "stop": 67200.0,
        "target": 71100.0,
        "context": "BTC breaking above 4h range resistance with volume expansion (vol_ratio=2.4). Bullish FVG confirmed at 68100. EMA20>EMA50>EMA200. RSI(14)=62. MACD hist=+14.2.",
    },
    {
        "id": "PROMPT_02_ETH_BEAR_BREAKDOWN",
        "symbol": "ETHUSDT",
        "direction": "SELL",
        "entry": 2480.0,
        "stop": 2540.0,
        "target": 2360.0,
        "context": "ETH rejected at 200-period EMA on 1h. Swing low swept with displacement. Bearish Order Block formed at 2510. RSI=38. MACD histogram decelerating negatively (-8.5).",
    },
    {
        "id": "PROMPT_03_SOL_RANGE_POC",
        "symbol": "SOLUSDT",
        "direction": "BUY",
        "entry": 164.5,
        "stop": 160.0,
        "target": 173.5,
        "context": "SOL trading inside horizontal range between 160 and 172. Currently at Point of Control. No clean displacement. Volume ratio=0.68. RSI=51. MACD hist=+0.02.",
    },
    {
        "id": "PROMPT_04_BTC_BEAR_DIVERGENCE",
        "symbol": "BTCUSDT",
        "direction": "SELL",
        "entry": 69800.0,
        "stop": 70600.0,
        "target": 68200.0,
        "context": "BTC prints higher high at 69800 but RSI prints lower high (79 vs 84 - bearish divergence). CVD shows buyer exhaustion at highs. Bearish pin bar closing near lows.",
    },
    {
        "id": "PROMPT_05_ETH_LIQUIDITY_SWEEP",
        "symbol": "ETHUSDT",
        "direction": "BUY",
        "entry": 2420.0,
        "stop": 2380.0,
        "target": 2500.0,
        "context": "ETH swept equal lows at 2390 into HTF demand block and aggressively closed back above within 15m. Long lower shadow wick. RSI=35 recovering upward. Vol_ratio=2.8.",
    },
    {
        "id": "PROMPT_06_SOL_BULL_PULLBACK",
        "symbol": "SOLUSDT",
        "direction": "BUY",
        "entry": 172.0,
        "stop": 168.0,
        "target": 180.0,
        "context": "SOL in daily uptrend pulls back to unmitigated 15m Bullish OB at 171.5. Trendline support holding. EMA20>EMA50. RSI=48 rebounding. Spread=0.02%.",
    },
    {
        "id": "PROMPT_07_BNB_SUPPLY_REJECTION",
        "symbol": "BNBUSDT",
        "direction": "SELL",
        "entry": 595.0,
        "stop": 605.0,
        "target": 575.0,
        "context": "BNB tests major resistance at 600 psychological round level. High volume wick rejection. Bearish fair value gap created between 598 and 594. RSI=69 turning down.",
    },
    {
        "id": "PROMPT_08_BTC_HIGH_VOL_NEWS",
        "symbol": "BTCUSDT",
        "direction": "BUY",
        "entry": 67400.0,
        "stop": 65500.0,
        "target": 71200.0,
        "context": "Extreme 1m volatility during economic release. Spread widened to 0.15%. Rapid whipsaws between 66800 and 67800. ATR 3x higher than 20-period average.",
    },
    {
        "id": "PROMPT_09_ETH_LOW_VOL_CHOP",
        "symbol": "ETHUSDT",
        "direction": "SELL",
        "entry": 2450.0,
        "stop": 2470.0,
        "target": 2410.0,
        "context": "Weekend low-volume consolidation. ATR compressed to 0.2%. Order book depth thin. No order block structure formed. RSI=50 flat. MACD flat.",
    },
    {
        "id": "PROMPT_10_SOL_BEAR_CONTINUATION",
        "symbol": "SOLUSDT",
        "direction": "SELL",
        "entry": 158.0,
        "stop": 162.5,
        "target": 149.0,
        "context": "SOL breaks below 4h bear flag consolidation. EMA20<EMA50<EMA200 stack. Bearish displacement candle with volume ratio 1.9. RSI=32 declining.",
    },
    {
        "id": "PROMPT_11_BTC_FAKEOUT_REVERSAL",
        "symbol": "BTCUSDT",
        "direction": "SELL",
        "entry": 68900.0,
        "stop": 69500.0,
        "target": 67700.0,
        "context": "BTC attempted breakout above 69200 resistance, immediately trapped breakout buyers and closed below the range high as a bearish engulfing candle. SFP pattern.",
    },
    {
        "id": "PROMPT_12_ETH_OVERSOLD_CAPITULATION",
        "symbol": "ETHUSDT",
        "direction": "BUY",
        "entry": 2350.0,
        "stop": 2290.0,
        "target": 2470.0,
        "context": "ETH plunges into daily support level. RSI=21 (extreme oversold). Massive volume absorption spike on candle bottom with bullish divergence developing.",
    },
]

SYSTEM_PROMPT = (
    "You are an institutional crypto quantitative risk and debate committee. "
    "Deliberate the proposed trade from Bull, Bear, and Risk Moderator perspectives simultaneously. "
    "Respond STRICTLY in JSON format with exactly these keys: "
    "bull_thesis (string, max 15 words), "
    "bear_thesis (string, max 15 words), "
    "risk_verdict (string: APPROVE or VETO), "
    "conviction (integer 1 to 10), "
    "consensus_action (string: BUY, SELL, or STAND_ASIDE), "
    "reason (string, max 15 words)."
)


def call_ollama(model: str, prompt: str, host: str = "http://127.0.0.1:11434", timeout_sec: float = 60.0) -> Dict[str, Any]:
    url = f"{host.rstrip('/')}/api/generate"
    full_prompt = f"{SYSTEM_PROMPT}\n\nPROPOSED TRADE:\n{prompt}\n\nJSON OUTPUT:"
    payload = {
        "model": model,
        "prompt": full_prompt,
        "think": False,
        "format": "json",
        "stream": False,
        "keep_alive": "15m",
        "options": {
            "temperature": 0.0,
            "num_predict": 110,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latency = time.perf_counter() - t0
        eval_count = data.get("eval_count", 0)
        eval_duration = data.get("eval_duration", 1)  # nanoseconds
        tps = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0.0
        return {
            "success": True,
            "latency": latency,
            "response": data.get("response", ""),
            "eval_count": eval_count,
            "tokens_per_sec": tps,
            "error": "",
        }
    except Exception as exc:
        latency = time.perf_counter() - t0
        return {
            "success": False,
            "latency": latency,
            "response": "",
            "eval_count": 0,
            "tokens_per_sec": 0.0,
            "error": str(exc),
        }


def validate_json_response(raw_text: str) -> Tuple[bool, Dict[str, Any], str]:
    try:
        parsed = json.loads(raw_text)
        required = ["bull_thesis", "bear_thesis", "risk_verdict", "conviction", "consensus_action", "reason"]
        missing = [k for k in required if k not in parsed]
        if missing:
            return False, {}, f"Missing keys: {missing}"
        return True, parsed, ""
    except Exception as e:
        return False, {}, f"JSON parse error: {e}"


def run_benchmark(models: List[str], output_csv: Path) -> Dict[str, Any]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    print(f"\n================================================================================")
    print(f"BENCHMARKING DEBATE LLMs: {models}")
    print(f"Prompts: {len(BENCHMARK_PROMPTS)} real market setups per model")
    print(f"Parameters: think=False, format=json, temperature=0.0, num_predict=110, keep_alive=15m")
    print(f"================================================================================\n")

    summary_by_model: Dict[str, Dict[str, Any]] = {}

    for model in models:
        print(f"--- Starting evaluation for model: {model} ---")
        latencies: List[float] = []
        warm_latencies: List[float] = []
        tps_list: List[float] = []
        valid_json_count = 0
        timeout_count = 0
        cold_start_latency = 0.0

        for i, item in enumerate(BENCHMARK_PROMPTS):
            prompt_text = (
                f"Symbol: {item['symbol']} | Direction: {item['direction']} | "
                f"Entry: {item['entry']} | Stop: {item['stop']} | Target: {item['target']}\n"
                f"Setup Context: {item['context']}"
            )
            print(f"  [{model}] Prompt {i+1}/{len(BENCHMARK_PROMPTS)}: {item['id']} ... ", end="", flush=True)

            res = call_ollama(model=model, prompt=prompt_text, timeout_sec=60.0)
            latency = res["latency"]
            latencies.append(latency)

            if i == 0:
                cold_start_latency = latency
            else:
                warm_latencies.append(latency)

            is_valid_json = False
            parsed_data = {}
            json_err = ""

            if res["success"]:
                is_valid, parsed, err_msg = validate_json_response(res["response"])
                is_valid_json = is_valid
                parsed_data = parsed
                json_err = err_msg
                if is_valid:
                    valid_json_count += 1
                tps = res["tokens_per_sec"]
                tps_list.append(tps)
                status_str = f"OK ({latency:.2f}s, {tps:.1f} t/s, JSON: {'VALID' if is_valid else 'INVALID'})"
            else:
                if "timed out" in res["error"].lower():
                    timeout_count += 1
                status_str = f"FAILED: {res['error']} ({latency:.2f}s)"

            print(status_str)

            results.append({
                "model": model,
                "prompt_id": item["id"],
                "symbol": item["symbol"],
                "latency_sec": round(latency, 3),
                "is_cold_start": (i == 0),
                "eval_tokens": res["eval_count"],
                "tokens_per_sec": round(res["tokens_per_sec"], 2),
                "success": res["success"],
                "valid_json": is_valid_json,
                "risk_verdict": parsed_data.get("risk_verdict", ""),
                "conviction": parsed_data.get("conviction", ""),
                "consensus_action": parsed_data.get("consensus_action", ""),
                "error": res["error"] or json_err,
                "raw_response": res["response"][:150].replace("\n", " "),
            })

        # Calculate statistics
        p50 = statistics.median(latencies) if latencies else 0.0
        # p95: quantile 0.95 or max of remaining
        sorted_lat = sorted(latencies)
        p95_idx = int(round(0.95 * (len(sorted_lat) - 1)))
        p95 = sorted_lat[p95_idx] if sorted_lat else 0.0
        avg_warm = statistics.mean(warm_latencies) if warm_latencies else 0.0
        avg_tps = statistics.mean(tps_list) if tps_list else 0.0
        valid_rate = (valid_json_count / len(BENCHMARK_PROMPTS)) * 100.0
        timeout_rate = (timeout_count / len(BENCHMARK_PROMPTS)) * 100.0

        summary_by_model[model] = {
            "cold_start_sec": round(cold_start_latency, 2),
            "avg_warm_sec": round(avg_warm, 2),
            "p50_sec": round(p50, 2),
            "p95_sec": round(p95, 2),
            "avg_tokens_per_sec": round(avg_tps, 2),
            "valid_json_rate_pct": round(valid_rate, 1),
            "timeout_rate_pct": round(timeout_rate, 1),
            "sample_count": len(BENCHMARK_PROMPTS),
        }

    # Write CSV
    with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "model", "prompt_id", "symbol", "latency_sec", "is_cold_start",
            "eval_tokens", "tokens_per_sec", "success", "valid_json",
            "risk_verdict", "conviction", "consensus_action", "error", "raw_response"
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n================================================================================")
    print(f"BENCHMARK RESULTS SUMMARY (Saved to {output_csv}):")
    print(f"================================================================================")
    for model, stats in summary_by_model.items():
        print(f"\nModel: {model}")
        print(f"  - Cold Start Latency:     {stats['cold_start_sec']} s")
        print(f"  - Warm Average Latency:   {stats['avg_warm_sec']} s")
        print(f"  - p50 Latency:            {stats['p50_sec']} s")
        print(f"  - p95 Latency:            {stats['p95_sec']} s")
        print(f"  - Tokens / Second (Avg):  {stats['avg_tokens_per_sec']} t/s")
        print(f"  - Valid JSON Rate:        {stats['valid_json_rate_pct']}%")
        print(f"  - Timeout Rate:           {stats['timeout_rate_pct']}%")

    return summary_by_model


if __name__ == "__main__":
    csv_dest = Path("work/reports/ollama_benchmark_results.csv")
    models_to_test = ["laya-crypto:latest", "gemma4:12b"]
    run_benchmark(models_to_test, csv_dest)
