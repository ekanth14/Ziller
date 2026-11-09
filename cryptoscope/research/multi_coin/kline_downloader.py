"""4-Year 1h Kline Data Ingestion for Multi-Coin Universe (Phase 4.1).

Downloads 4 years of 1h klines from Binance Spot public REST API, saving to Parquet
storage isolated from the production SQLite databases.
Strict boundary: Never goes back further than exactly 4 years from ingestion time.
"""

import datetime
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("cryptoscope.research.multi_coin.kline_downloader")

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
PARQUET_BASE_DIR = Path("data/parquet_klines/1h")

# 4 years in milliseconds: 4 * 365 * 24 * 3600 * 1000
FOUR_YEARS_MS = 4 * 365 * 24 * 3600 * 1000


def get_four_year_window() -> Tuple[int, int]:
    """Return (start_time_ms, end_time_ms) bounded to exactly 4 years."""
    now_ms = int(time.time() * 1000)
    start_time_ms = now_ms - FOUR_YEARS_MS
    return start_time_ms, now_ms


def fetch_klines_chunk(
    symbol: str,
    interval: str = "1h",
    start_time_ms: int = 0,
    end_time_ms: Optional[int] = None,
    limit: int = 1000,
    timeout: float = 15.0,
) -> List[List[Any]]:
    """Fetch up to 1000 klines from Binance public endpoint."""
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "limit": limit,
    }
    if end_time_ms:
        params["endTime"] = end_time_ms

    url = f"{BINANCE_KLINES_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ZILLERS-MultiCoin-Ingest/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_symbol_4y(
    symbol: str,
    output_dir: Path = PARQUET_BASE_DIR,
    interval: str = "1h",
    rate_limit_delay: float = 0.15,
) -> Dict[str, Any]:
    """Download 4 years of klines for a single symbol and persist to Parquet."""
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / f"{symbol}.parquet"

    start_ms, end_ms = get_four_year_window()
    current_start = start_ms

    all_rows: List[Dict[str, Any]] = []
    chunk_count = 0
    delisted_or_empty = False

    while current_start < end_ms:
        try:
            chunk = fetch_klines_chunk(
                symbol=symbol,
                interval=interval,
                start_time_ms=current_start,
                end_time_ms=end_ms,
                limit=1000
            )
        except urllib.error.HTTPError as err:
            if err.code in (400, 404):
                # Symbol invalid or delisted and pruned from REST
                delisted_or_empty = True
                break
            elif err.code == 429:
                logger.warning("Rate limit encountered for %s. Sleeping 5s...", symbol)
                time.sleep(5.0)
                continue
            else:
                raise

        if not chunk:
            break

        chunk_count += 1
        for row in chunk:
            open_ts = int(row[0])
            # Enforce strict 4-year lower boundary
            if open_ts < start_ms:
                continue
            all_rows.append({
                "open_time": open_ts,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": int(row[6]),
                "quote_volume": float(row[7]),
                "trades": int(row[8]),
                "taker_buy_volume": float(row[9]),
                "taker_buy_quote_volume": float(row[10]),
            })

        last_open_ts = int(chunk[-1][0])
        # If no forward progress or end reached, break
        if last_open_ts <= current_start or len(chunk) < 1000:
            break
        current_start = last_open_ts + 1
        time.sleep(rate_limit_delay)

    if not all_rows:
        return {
            "symbol": symbol,
            "status": "DELISTED_OR_NO_DATA" if delisted_or_empty else "EMPTY",
            "bars_count": 0,
            "parquet_path": None,
            "start_time": None,
            "end_time": None,
            "chunks_fetched": chunk_count,
        }

    df = pd.DataFrame(all_rows)
    # Deduplicate on open_time and sort ascending
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)

    # Save to Parquet via fastparquet
    df.to_parquet(parquet_path, engine="fastparquet", index=False)

    min_ts = int(df["open_time"].min())
    max_ts = int(df["open_time"].max())
    min_dt = datetime.datetime.fromtimestamp(min_ts / 1000, tz=datetime.timezone.utc).isoformat()
    max_dt = datetime.datetime.fromtimestamp(max_ts / 1000, tz=datetime.timezone.utc).isoformat()

    return {
        "symbol": symbol,
        "status": "DOWNLOADED",
        "bars_count": len(df),
        "parquet_path": str(parquet_path),
        "start_time": min_dt,
        "end_time": max_dt,
        "start_ts_ms": min_ts,
        "end_ts_ms": max_ts,
        "chunks_fetched": chunk_count,
    }


def download_universe_4y(
    symbols: List[str],
    output_dir: Path = PARQUET_BASE_DIR,
    manifest_path: Path = Path("data/parquet_klines/manifest.json"),
) -> Dict[str, Any]:
    """Download 4-year klines for a list of symbols and record manifest."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    downloaded_count = 0
    no_data_count = 0

    print(f"[INGESTION] Starting 4-year 1h klines download for {len(symbols)} symbols...", flush=True)
    for idx, sym in enumerate(symbols, 1):
        print(f"[{idx}/{len(symbols)}] Ingesting {sym}...", flush=True)
        res = download_symbol_4y(sym, output_dir=output_dir)
        results[sym] = res
        if res["status"] == "DOWNLOADED":
            downloaded_count += 1
            print(f"   -> {res['bars_count']} bars ({res['start_time'][:10]} to {res['end_time'][:10]})", flush=True)
        else:
            no_data_count += 1
            print(f"   -> {res['status']}", flush=True)

    summary = {
        "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_symbols_requested": len(symbols),
        "downloaded_count": downloaded_count,
        "no_data_count": no_data_count,
        "output_directory": str(output_dir),
        "symbols": results,
    }
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[INGESTION] Completed: {downloaded_count} downloaded, {no_data_count} without data. Manifest saved to {manifest_path}", flush=True)
    return summary


if __name__ == "__main__":
    from cryptoscope.research.multi_coin.candidate_universe import build_candidate_universe
    universe = build_candidate_universe()
    # Ingest core benchmark symbols + sample of active and historical delisted
    targets = universe["core_benchmark_symbols"] + ["LUNAUSDT", "FTTUSDT", "BUSDUSDT"]
    download_universe_4y(targets)
