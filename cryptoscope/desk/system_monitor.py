"""Device hardware, process, network latency and market-data delay snapshot for the System page."""
from __future__ import annotations

import os
import platform
import socket
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen

import psutil

# Public endpoints only; each probe is a single lightweight GET.
PING_TARGETS = (
    ("Binance REST", "https://api.binance.com/api/v3/ping"),
    ("Binance data", "https://data-api.binance.vision/api/v3/ping"),
    ("Binance testnet", "https://testnet.binance.vision/api/v3/ping"),
    ("Coinbase", "https://api.exchange.coinbase.com/time"),
    ("Kraken", "https://api.kraken.com/0/public/Time"),
    ("CoinGecko", "https://api.coingecko.com/api/v3/ping"),
)
BINANCE_TIME = "https://api.binance.com/api/v3/time"


def _http_rtt(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        req = Request(url, headers={"User-Agent": "ZILLERS-Monitor/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed public hosts
            resp.read(2048)
            status = resp.status
        return {"ok": 200 <= status < 300, "status": status, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "status": None, "ms": None, "error": type(exc).__name__}


def _clock_offset_ms() -> Optional[float]:
    """Exchange clock minus local clock (NTP-style midpoint estimate)."""
    try:
        t0 = time.time()
        with urlopen(Request(BINANCE_TIME, headers={"User-Agent": "ZILLERS-Monitor/1.0"}), timeout=3) as resp:  # noqa: S310
            import json
            server = json.loads(resp.read())["serverTime"] / 1000.0
        t1 = time.time()
        return round((server - (t0 + t1) / 2) * 1000, 1)
    except Exception:
        return None


class SystemMonitor:
    """Thread-safe sampler. Network probes are cached (default 5 s) so polling never floods hosts."""

    def __init__(self, ping_ttl: float = 5.0, feed_status: Optional[Callable[[], Dict[str, Any]]] = None,
                 extra_targets: tuple = (), history: int = 60):
        self.ping_ttl = ping_ttl
        self.feed_status = feed_status
        self.targets = PING_TARGETS + tuple(extra_targets)
        self.history_len = history
        self._lock = threading.Lock()
        self._ping_cache: tuple[float, Dict[str, Any]] | None = None
        self._last_net: tuple[float, Any] | None = None
        self._history: Dict[str, List[Any]] = {}
        psutil.cpu_percent(interval=None)  # prime the counter
        self._proc = psutil.Process(os.getpid())
        self._proc.cpu_percent(interval=None)

    # ---------------------------------------------------------- hardware
    def hardware(self) -> Dict[str, Any]:
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        freq = psutil.cpu_freq()
        disks = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            disks.append({"mount": part.mountpoint, "fs": part.fstype, "total_gb": round(u.total / 1e9, 1),
                          "used_gb": round(u.used / 1e9, 1), "percent": u.percent})
        now, io = time.time(), psutil.net_io_counters()
        rates = {"sent_kbps": None, "recv_kbps": None}
        with self._lock:
            if self._last_net:
                dt = max(1e-6, now - self._last_net[0])
                rates = {"sent_kbps": round((io.bytes_sent - self._last_net[1].bytes_sent) / dt / 1024, 1),
                         "recv_kbps": round((io.bytes_recv - self._last_net[1].bytes_recv) / dt / 1024, 1)}
            self._last_net = (now, io)
        battery = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                battery = {"percent": b.percent, "plugged": b.power_plugged,
                           "secs_left": None if b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else b.secsleft}
        except Exception:
            pass
        with self._proc.oneshot():
            proc = {"pid": self._proc.pid, "cpu_percent": self._proc.cpu_percent(interval=None),
                    "rss_mb": round(self._proc.memory_info().rss / 1e6, 1), "threads": self._proc.num_threads(),
                    "connections": len(self._proc.net_connections(kind="inet")) if hasattr(self._proc, "net_connections") else None,
                    "uptime_s": round(now - self._proc.create_time())}
        return {
            "host": socket.gethostname(), "os": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
            "cpu_model": platform.processor(), "python": sys.version.split()[0],
            "boot_time": psutil.boot_time(), "uptime_s": round(now - psutil.boot_time()),
            "cpu": {"percent": psutil.cpu_percent(interval=None), "per_core": psutil.cpu_percent(interval=None, percpu=True),
                    "cores_logical": psutil.cpu_count(), "cores_physical": psutil.cpu_count(logical=False),
                    "freq_mhz": None if freq is None else round(freq.current)},
            "memory": {"total_gb": round(vm.total / 1e9, 1), "used_gb": round(vm.used / 1e9, 1), "percent": vm.percent,
                       "swap_percent": sw.percent},
            "disks": disks,
            "network": {**rates, "sent_mb": round(io.bytes_sent / 1e6, 1), "recv_mb": round(io.bytes_recv / 1e6, 1),
                        "errors": io.errin + io.errout, "drops": io.dropin + io.dropout},
            "battery": battery,
            "process": proc,
        }

    # ---------------------------------------------------------- network
    def pings(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if self._ping_cache and now - self._ping_cache[0] < self.ping_ttl:
                return self._ping_cache[1]
        results: Dict[str, Any] = {}
        threads = []

        def run(name, url):
            results[name] = _http_rtt(url)

        for name, url in self.targets:
            th = threading.Thread(target=run, args=(name, url), daemon=True)
            th.start()
            threads.append(th)
        for th in threads:
            th.join(4.0)
        rows = [{"name": n, "url": u, **results.get(n, {"ok": False, "ms": None, "error": "Timeout"})} for n, u in self.targets]
        snap = {"targets": rows, "clock_offset_ms": _clock_offset_ms(), "measured_at": now}
        with self._lock:
            self._ping_cache = (now, snap)
            for r in rows:
                h = self._history.setdefault(r["name"], [])
                h.append(r["ms"])
                del h[:-self.history_len]
        return snap

    def snapshot(self) -> Dict[str, Any]:
        feeds = {}
        if self.feed_status:
            try:
                feeds = self.feed_status()
            except Exception as exc:
                feeds = {"error": type(exc).__name__}
        pings = self.pings()
        with self._lock:
            history = {k: list(v) for k, v in self._history.items()}
        return {"generated_at": time.time(), "hardware": self.hardware(), "latency": pings,
                "latency_history": history, "feeds": feeds}
