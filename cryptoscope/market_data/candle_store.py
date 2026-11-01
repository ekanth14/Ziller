"""SQLite WAL-mode persistent time-series candle archive for real crypto history."""
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional


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

    def save_candles(self, symbol: str, interval: str, candles: List[Dict[str, Any]], source: str = "binance") -> int:
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
                        float(c["open_time"]),
                        float(c["close_time"]),
                        float(c["open"]),
                        float(c["high"]),
                        float(c["low"]),
                        float(c["close"]),
                        float(c.get("volume", 0.0)),
                        float(c.get("taker_buy_volume", 0.0)),
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
