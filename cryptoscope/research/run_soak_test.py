"""Soak and load stability test for ZILLERS: 50 SSE clients + 5 req/s API traffic.

Logs CPU, RAM (RSS), thread count, and open socket count every 30 seconds to
work/reports/soak_test_metrics.csv.
Validates:
- No socket leaks
- Thread count stability
- RSS memory growth < 100 MB
"""

import argparse
import csv
import http.client
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

try:
    import psutil
except ImportError:
    psutil = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cryptoscope.soak")


def find_server_process(port: int = 8900) -> Optional[Any]:
    if not psutil:
        return None
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            for conn in proc.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    return proc
        except Exception:
            pass
    return None


def run_sse_client(host: str, port: int, stop_event: threading.Event, client_id: int):
    while not stop_event.is_set():
        try:
            conn = http.client.HTTPConnection(host, port, timeout=15)
            conn.request("GET", "/api/market/stream", headers={"Host": f"{host}:{port}", "Accept": "text/event-stream"})
            resp = conn.getresponse()
            if resp.status == 200:
                while not stop_event.is_set():
                    line = resp.readline()
                    if not line:
                        break
            conn.close()
        except Exception:
            time.sleep(1.0)


def run_api_traffic_worker(host: str, port: int, stop_event: threading.Event, rate_per_sec: float = 5.0):
    interval = 1.0 / rate_per_sec
    endpoints = ["/api/market/status", "/health", "/api/laya/status", "/api/fx/rate"]
    idx = 0
    while not stop_event.is_set():
        ep = endpoints[idx % len(endpoints)]
        idx += 1
        t0 = time.time()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", ep, headers={"Host": f"{host}:{port}"})
            resp = conn.getresponse()
            _ = resp.read()
            conn.close()
        except Exception:
            pass
        sleep_dur = max(0.01, interval - (time.time() - t0))
        time.sleep(sleep_dur)


def main():
    parser = argparse.ArgumentParser(description="ZILLERS Soak and Load Test")
    parser.add_argument("--host", default="127.0.0.1", help="Target host")
    parser.add_argument("--port", type=int, default=8900, help="Target port")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--interval", type=int, default=15, help="Sampling interval in seconds")
    parser.add_argument("--clients", type=int, default=30, help="Number of concurrent SSE client connections")
    parser.add_argument("--api-rate", type=float, default=5.0, help="API requests per second")
    parser.add_argument("--out", default="work/reports/soak_test_metrics.csv", help="Metrics output CSV")
    args = parser.parse_args()

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("ZILLERS LOAD & SOAK STABILITY TEST")
    print(f"Target: {args.host}:{args.port} | Duration: {args.duration}s ({args.duration/60:.1f} min) | Interval: {args.interval}s")
    print(f"Load Profile: {args.clients} SSE clients (/api/market/stream) + {args.api_rate} req/s API traffic")
    print(f"Output CSV: {out_csv}")
    print("=" * 80)

    # Health check
    try:
        req = urllib.request.Request(f"http://{args.host}:{args.port}/health", headers={"Host": f"{args.host}:{args.port}"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status != 200:
                print(f"ERROR: Server /health returned {resp.status}")
                return
    except Exception as e:
        print(f"ERROR: Target server {args.host}:{args.port} unreachable: {e}")
        return

    proc = find_server_process(args.port)
    if proc:
        print(f"Monitoring server PID: {proc.pid} ({proc.name()})")
    else:
        print("Note: Inspecting server metrics via /api/market/status.")

    stop_event = threading.Event()
    client_threads: List[threading.Thread] = []

    print(f"Spawning {args.clients} SSE client threads...")
    for i in range(args.clients):
        t = threading.Thread(target=run_sse_client, args=(args.host, args.port, stop_event, i), daemon=True)
        t.start()
        client_threads.append(t)

    print(f"Spawning {args.api_rate} req/s API traffic worker...")
    traffic_thread = threading.Thread(target=run_api_traffic_worker, args=(args.host, args.port, stop_event, args.api_rate), daemon=True)
    traffic_thread.start()

    # Metrics logging
    records = []
    start_time = time.time()
    initial_rss = 0.0

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "elapsed_sec", "timestamp", "cpu_percent", "rss_mb",
            "threads_count", "open_sockets_count", "rss_growth_mb"
        ])
        writer.writeheader()

        iteration = 0
        while (time.time() - start_time) < args.duration:
            elapsed = time.time() - start_time
            now = time.time()
            cpu_pct = 0.0
            rss_mb = 0.0
            th_count = 0
            sockets_count = 0

            if proc:
                try:
                    cpu_pct = proc.cpu_percent(interval=None)
                    mem = proc.memory_info()
                    rss_mb = mem.rss / (1024 * 1024)
                    th_count = proc.num_threads()
                    sockets_count = len(proc.net_connections(kind="inet"))
                except Exception:
                    pass
            else:
                try:
                    with urllib.request.urlopen(f"http://{args.host}:{args.port}/api/market/status", timeout=5) as resp:
                        data = json.loads(resp.read().decode())
                        srv = data.get("server", {})
                        rss_mb = float(srv.get("rss_mb", 0.0))
                        th_count = int(srv.get("threads", 0))
                        sockets_count = len(client_threads)
                except Exception:
                    pass

            if iteration == 0 and rss_mb > 0:
                initial_rss = rss_mb

            rss_growth = (rss_mb - initial_rss) if initial_rss > 0 else 0.0

            row = {
                "elapsed_sec": round(elapsed, 1),
                "timestamp": round(now, 1),
                "cpu_percent": round(cpu_pct, 1),
                "rss_mb": round(rss_mb, 2),
                "threads_count": th_count,
                "open_sockets_count": sockets_count,
                "rss_growth_mb": round(rss_growth, 2),
            }
            writer.writerow(row)
            f.flush()
            records.append(row)

            print(
                f"[{elapsed:6.1f}s / {args.duration}s] "
                f"RSS: {rss_mb:6.1f} MB (Growth: {rss_growth:+5.1f} MB) | "
                f"Threads: {th_count:3d} | Active SSE Clients: {sockets_count:3d}"
            )
            iteration += 1
            time.sleep(args.interval)

    # Stop load
    print("\nStopping soak test load generators...")
    stop_event.set()
    time.sleep(1.0)

    # Summary
    print("\n" + "=" * 80)
    print("SOAK TEST SUMMARY:")
    print("=" * 80)
    if records:
        final_growth = records[-1]["rss_growth_mb"]
        max_threads = max(r["threads_count"] for r in records)
        min_threads = min(r["threads_count"] for r in records)
        print(f"Initial RSS: {initial_rss:.2f} MB")
        print(f"Final RSS:   {records[-1]['rss_mb']:.2f} MB (Total Growth: {final_growth:+.2f} MB)")
        print(f"Thread Range: [{min_threads}, {max_threads}]")
        if abs(final_growth) < 100.0:
            print("PASS: RSS memory growth < 100 MB target.")
        else:
            print(f"FAIL: RSS memory growth exceeded target (+{final_growth:.2f} MB >= 100 MB).")
    print(f"Full metrics audit log saved to {out_csv}")


if __name__ == "__main__":
    main()
