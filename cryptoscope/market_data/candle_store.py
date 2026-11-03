"""SQLite WAL-mode persistent time-series candle archive for real crypto history."""
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cryptoscope.candle_store")


class CandleStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path(__file__).resolve().parents[2] / "work/runtime/crypto_candles.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS crypto_candles (
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        open_time REAL NOT NULL,
                        close_time REAL NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,
                        taker_buy_volume REAL NOT NULL,
                        source TEXT NOT NULL,
                        created_at REAL DEFAULT (strftime('%s', 'now')),
                        PRIMARY KEY (symbol, interval, open_time)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_candles_lookup 
                    ON crypto_candles(symbol, interval, close_time DESC)
                """)
                conn.commit()
            finally:
                conn.close()

    def save_candles(self, symbol: str, interval: str, candles: List[Any], source: str = "binance") -> int:
        if not candles:
            return 0
        inserted = 0
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                rows = [
                    (
                        symbol,
                        interval,
                        float(c["open_time"] if isinstance(c, dict) else c.open_time),
                        float(c["close_time"] if isinstance(c, dict) else c.close_time),
                        float(c["open"] if isinstance(c, dict) else c.open),
                        float(c["high"] if isinstance(c, dict) else c.high),
                        float(c["low"] if isinstance(c, dict) else c.low),
                        float(c["close"] if isinstance(c, dict) else c.close),
                        float((c.get("volume", 0.0) if isinstance(c, dict) else getattr(c, "volume", 0.0)) or 0.0),
                        float((c.get("taker_buy_volume", 0.0) if isinstance(c, dict) else getattr(c, "taker_buy_volume", 0.0)) or 0.0),
                        source,
                    )
                    for c in candles
                ]
                cur.executemany("""
                    INSERT OR REPLACE INTO crypto_candles 
                    (symbol, interval, open_time, close_time, open, high, low, close, volume, taker_buy_volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                inserted = cur.rowcount
            finally:
                conn.close()
        return inserted

    def load_candles(self, symbol: str, interval: str, limit: int = 200, before: Optional[float] = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if before is not None:
                    cur.execute("""
                        SELECT open_time, close_time, open, high, low, close, volume, taker_buy_volume, source
                        FROM crypto_candles
                        WHERE symbol = ? AND interval = ? AND close_time <= ?
                        ORDER BY open_time DESC LIMIT ?
                    """, (symbol, interval, before, limit))
                else:
                    cur.execute("""
                        SELECT open_time, close_time, open, high, low, close, volume, taker_buy_volume, source
                        FROM crypto_candles
                        WHERE symbol = ? AND interval = ?
                        ORDER BY open_time DESC LIMIT ?
                    """, (symbol, interval, limit))
                rows = cur.fetchall()
                # Return in chronological order
                return [dict(r) for r in reversed(rows)]
            finally:
                conn.close()

    @staticmethod
    def interval_seconds(interval: str) -> int:
        """Convert standard interval notation (1m, 5m, 15m, 1h, 1d) into duration seconds."""
        if not interval:
            return 300
        unit = interval[-1].lower()
        val = int(interval[:-1]) if interval[:-1].isdigit() else 1
        if unit == 's':
            return max(1, val)
        if unit == 'm':
            return max(1, val * 60)
        if unit == 'h':
            return max(1, val * 3600)
        if unit == 'd':
            return max(1, val * 86400)
        if unit == 'w':
            return max(1, val * 604800)
        return 300

    def get_fresh_candles(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 100,
        max_age_multiplier: float = 2.0
    ) -> List[Dict[str, Any]]:
        """Load candles from SQLite; if missing, insufficient, or stale (> 2*interval), pull fresh live klines from Binance."""
        candles = self.load_candles(symbol, interval, limit=limit)
        sec = self.interval_seconds(interval)
        now = time.time()
        is_stale = False

        if not candles or len(candles) < min(limit, 20):
            is_stale = True
        else:
            latest_close = float(candles[-1].get("close_time") or 0.0)
            if (now - latest_close) > max(sec * max_age_multiplier, 120.0):
                is_stale = True

        if is_stale:
            try:
                from cryptoscope.providers.binance import BinanceProvider
                provider = BinanceProvider()
                snap = provider.snapshot(symbol, interval)
                if snap and snap.candles:
                    self.save_candles(symbol, interval, snap.candles, source="binance")
                    fresh = self.load_candles(symbol, interval, limit=limit)
                    if fresh:
                        return fresh
                    return [c if isinstance(c, dict) else c.__dict__ for c in snap.candles[-limit:]]
            except Exception as e:
                logger.debug("Live snapshot fetch for %s (%s) skipped: %s", symbol, interval, e)

        return candles
