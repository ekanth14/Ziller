"""Real-time foreign exchange rate service for secondary display conversions.

Follows strict truthfulness rules:
- Zero hardcoded seed rates; returns 'unavailable' until a real network fetch succeeds.
- Exposes rate age in seconds.
- Marks rate as 'stale' after 6 hours without fresh upstream confirmation.
- Logs all fetch errors with detailed messages.
"""

import json
import logging
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("cryptoscope.fx")


class FxRateService:
    DEFAULT_ENDPOINT = "https://open.er-api.com/v6/latest/USD"
    STALE_THRESHOLD_SECONDS = 6 * 3600  # 6 hours
    CACHE_TTL_SECONDS = 3600            # Refresh hourly

    def __init__(self, endpoint: Optional[str] = None, cache_ttl: int = CACHE_TTL_SECONDS):
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.cache_ttl = cache_ttl
        self.rates: Dict[str, float] = {}
        self.last_fetch: float = 0.0
        self.last_attempt: float = 0.0
        self.last_error: Optional[str] = None
        self.source: Optional[str] = None
        self._lock = threading.Lock()

    def get_rate(self, target: str = "INR", auto_fetch: bool = True) -> Dict[str, Any]:
        """Return rate dictionary with status: 'available' | 'stale' | 'unavailable'."""
        with self._lock:
            now = time.time()
            needs_fetch = (now - self.last_fetch > self.cache_ttl) and (now - self.last_attempt > 60)
            if auto_fetch and needs_fetch:
                self._fetch_locked(now)

            if not self.rates or target not in self.rates:
                return {
                    "status": "unavailable",
                    "target": target,
                    "rate": None,
                    "age_seconds": None,
                    "source": self.source,
                    "error": self.last_error,
                }

            age = now - self.last_fetch
            status = "stale" if age > self.STALE_THRESHOLD_SECONDS else "available"
            return {
                "status": status,
                "target": target,
                "rate": float(self.rates[target]),
                "age_seconds": round(age, 1),
                "source": self.source,
                "error": self.last_error if status == "stale" else None,
            }

    def fetch_now(self) -> bool:
        """Force synchronous fetch."""
        with self._lock:
            return self._fetch_locked(time.time())

    def _fetch_locked(self, now: float) -> bool:
        self.last_attempt = now
        try:
            req = Request(
                self.endpoint,
                headers={"User-Agent": "ZILLERS-Quant-Terminal/4.2 (FX Service)"},
            )
            with urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("result") == "success" and "rates" in data:
                self.rates = {k: float(v) for k, v in data["rates"].items()}
                self.last_fetch = now
                self.last_error = None
                self.source = "open_er_api"
                logger.info("FX exchange rates updated successfully (%d currencies)", len(self.rates))
                return True
            else:
                err_msg = f"Unexpected FX response format: {data.get('error-type', 'unknown')}"
                self.last_error = err_msg
                logger.warning("FX fetch warning: %s", err_msg)
                return False
        except (URLError, TimeoutError, ValueError, OSError) as err:
            err_msg = f"FX fetch failed from {self.endpoint}: {err}"
            self.last_error = err_msg
            logger.error("FX rate fetch error: %s", err_msg)
            return False
