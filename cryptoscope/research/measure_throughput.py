"""Measure API endpoint throughput (req/s) with and without keep-alive."""

import http.client
import json
import time
from typing import Dict, Any


def benchmark_endpoint_no_keepalive(host: str, port: int, path: str, requests_count: int = 200) -> Dict[str, Any]:
    """Measure throughput opening a new TCP connection on every request."""
    latencies = []
    t0 = time.perf_counter()
    successful = 0

    for _ in range(requests_count):
        req_start = time.perf_counter()
        conn = http.client.HTTPConnection(host, port, timeout=5)
        try:
            conn.request("GET", path, headers={"Host": f"{host}:{port}", "Connection": "close"})
            resp = conn.getresponse()
            _ = resp.read()
            if resp.status == 200:
                successful += 1
            latencies.append((time.perf_counter() - req_start) * 1000.0)
        except Exception:
            pass
        finally:
            conn.close()

    total_time = time.perf_counter() - t0
    rps = successful / total_time if total_time > 0 else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "path": path,
        "mode": "without_keep_alive",
        "requests": requests_count,
        "successful": successful,
        "total_time_sec": round(total_time, 3),
        "requests_per_sec": round(rps, 1),
        "avg_latency_ms": round(avg_latency, 2),
    }


def benchmark_endpoint_with_keepalive(host: str, port: int, path: str, requests_count: int = 500) -> Dict[str, Any]:
    """Measure throughput reusing a persistent HTTP keep-alive connection."""
    latencies = []
    t0 = time.perf_counter()
    successful = 0

    conn = http.client.HTTPConnection(host, port, timeout=5)
    for _ in range(requests_count):
        req_start = time.perf_counter()
        try:
            conn.request("GET", path, headers={"Host": f"{host}:{port}", "Connection": "keep-alive"})
            resp = conn.getresponse()
            _ = resp.read()
            if resp.status == 200:
                successful += 1
            latencies.append((time.perf_counter() - req_start) * 1000.0)
        except Exception:
            conn.close()
            conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.close()

    total_time = time.perf_counter() - t0
    rps = successful / total_time if total_time > 0 else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "path": path,
        "mode": "with_keep_alive",
        "requests": requests_count,
        "successful": successful,
        "total_time_sec": round(total_time, 3),
        "requests_per_sec": round(rps, 1),
        "avg_latency_ms": round(avg_latency, 2),
    }


def main():
    host = "127.0.0.1"
    port = 8900
    endpoints = ["/api/market/status", "/api/laya/status"]

    print("================================================================================")
    print(f"BENCHMARKING API THROUGHPUT ON {host}:{port}")
    print("================================================================================\n")

    results = []
    for path in endpoints:
        print(f"Testing {path} (without keep-alive) ... ", end="", flush=True)
        res_no_ka = benchmark_endpoint_no_keepalive(host, port, path, requests_count=150)
        print(f"{res_no_ka['requests_per_sec']} req/s (avg latency: {res_no_ka['avg_latency_ms']} ms)")
        results.append(res_no_ka)

        print(f"Testing {path} (with keep-alive) ... ", end="", flush=True)
        res_ka = benchmark_endpoint_with_keepalive(host, port, path, requests_count=300)
        print(f"{res_ka['requests_per_sec']} req/s (avg latency: {res_ka['avg_latency_ms']} ms)")
        results.append(res_ka)

    print("\n" + "=" * 80)
    print(f"{'Endpoint':<25} | {'Mode':<20} | {'Throughput (req/s)':<20} | {'Avg Latency (ms)':<15}")
    print("-" * 80)
    for r in results:
        print(f"{r['path']:<25} | {r['mode']:<20} | {r['requests_per_sec']:<20} | {r['avg_latency_ms']:<15}")
    print("=" * 80)

    # Save to json report
    out_path = "work/reports/throughput_benchmark.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Throughput metrics saved to {out_path}\n")


if __name__ == "__main__":
    main()
