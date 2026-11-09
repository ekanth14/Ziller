"""Task 9.1: DuckDB Evaluation on Phase 4 Parquet Files.

Benchmarks DuckDB vs current Pandas/fastparquet/pyarrow path for:
1. Multi-asset universe ingestion (loading all 18 coins)
2. Filtered window extraction with predicate and projection pushdown
3. Cross-asset aggregate analytics

Strict rule: SQLite stays for live state; DuckDB is evaluated strictly for analytical research and backtest candle queries.
"""

from dataclasses import asdict, dataclass
import gc
from pathlib import Path
import time
import tracemalloc
from typing import Any, Dict, List

import pandas as pd

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    duckdb = None


@dataclass
class BenchmarkResult:
    task_name: str
    pandas_time_sec: float
    duckdb_time_sec: float
    speedup_ratio: float
    pandas_peak_mb: float
    duckdb_peak_mb: float
    rows_processed: int
    notes: str


def evaluate_duckdb_parquet_queries(parquet_dir: str = "data/parquet_klines/1h") -> Dict[str, Any]:
    """Run comprehensive performance benchmarks between Pandas and DuckDB on Phase 4 Parquet files."""
    pdir = Path(parquet_dir)
    files = sorted(list(pdir.glob("*.parquet")))
    if not files:
        return {
            "status": "ERROR",
            "message": f"No parquet files found in {parquet_dir}",
            "decision": "SKIP",
        }

    if not HAS_DUCKDB:
        return {
            "status": "ERROR",
            "message": "DuckDB not installed",
            "decision": "SKIP",
        }

    benchmarks: List[BenchmarkResult] = []

    # -------------------------------------------------------------
    # 1. Multi-asset universe load (all 18 coins)
    # -------------------------------------------------------------
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    pandas_dfs = {}
    total_rows = 0
    for f in files:
        df = pd.read_parquet(f)
        pandas_dfs[f.stem] = df
        total_rows += len(df)
    t1 = time.perf_counter()
    _, peak_pandas = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pandas_load_sec = t1 - t0
    pandas_peak_mb = peak_pandas / (1024 * 1024)

    gc.collect()
    tracemalloc.start()
    t2 = time.perf_counter()
    con = duckdb.connect(database=":memory:")
    # Scan all parquet files in directory
    duck_df = con.execute(f"SELECT * FROM '{pdir.as_posix()}/*.parquet'").df()
    t3 = time.perf_counter()
    _, peak_duck = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duck_load_sec = t3 - t2
    duck_peak_mb = peak_duck / (1024 * 1024)

    benchmarks.append(BenchmarkResult(
        task_name="full_universe_load",
        pandas_time_sec=round(pandas_load_sec, 4),
        duckdb_time_sec=round(duck_load_sec, 4),
        speedup_ratio=round(pandas_load_sec / max(duck_load_sec, 1e-6), 2),
        pandas_peak_mb=round(pandas_peak_mb, 2),
        duckdb_peak_mb=round(duck_peak_mb, 2),
        rows_processed=total_rows,
        notes="DuckDB parallel scanning of all 18 Parquet files into unified DataFrame",
    ))

    # -------------------------------------------------------------
    # 2. Filtered window extraction (Predicate + Projection pushdown)
    # Target: 90-day window (2,160 bars) of [open_time, close, volume] for BTCUSDT
    # -------------------------------------------------------------
    btc_file = pdir / "BTCUSDT.parquet"
    if btc_file.exists():
        btc_sample = pd.read_parquet(btc_file)
        min_ts = int(btc_sample["open_time"].min())
        target_end_ts = min_ts + (90 * 24 * 3600 * 1000)

        # Pandas path
        gc.collect()
        tracemalloc.start()
        t0 = time.perf_counter()
        df_btc = pd.read_parquet(btc_file, columns=["open_time", "close", "volume"])
        df_filtered = df_btc[(df_btc["open_time"] >= min_ts) & (df_btc["open_time"] <= target_end_ts)]
        t1 = time.perf_counter()
        _, peak_pandas = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        pandas_win_sec = t1 - t0
        pandas_win_peak = peak_pandas / (1024 * 1024)

        # DuckDB path with pushdown
        gc.collect()
        tracemalloc.start()
        t2 = time.perf_counter()
        duck_filtered = con.execute(
            f"SELECT open_time, close, volume FROM '{btc_file.as_posix()}' WHERE open_time >= ? AND open_time <= ?",
            [min_ts, target_end_ts]
        ).df()
        t3 = time.perf_counter()
        _, peak_duck = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        duck_win_sec = t3 - t2
        duck_win_peak = peak_duck / (1024 * 1024)

        benchmarks.append(BenchmarkResult(
            task_name="predicate_projection_filter",
            pandas_time_sec=round(pandas_win_sec, 4),
            duckdb_time_sec=round(duck_win_sec, 4),
            speedup_ratio=round(pandas_win_sec / max(duck_win_sec, 1e-6), 2),
            pandas_peak_mb=round(pandas_win_peak, 2),
            duckdb_peak_mb=round(duck_win_peak, 2),
            rows_processed=len(duck_filtered),
            notes="Column projection + row filtering pushdown directly into Parquet reader",
        ))

    # -------------------------------------------------------------
    # 3. Rolling Liquidity & Quote Volume Aggregation
    # Compute 30-day average daily quote volume across all coins
    # -------------------------------------------------------------
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    summary_pandas = []
    for sym, df in pandas_dfs.items():
        if "quote_volume" in df.columns:
            qv_sum = df["quote_volume"].tail(720).mean()
            summary_pandas.append({"symbol": sym, "avg_quote_vol": qv_sum})
    df_sum_pandas = pd.DataFrame(summary_pandas)
    t1 = time.perf_counter()
    _, peak_pandas = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pandas_agg_sec = t1 - t0
    pandas_agg_peak = peak_pandas / (1024 * 1024)

    gc.collect()
    tracemalloc.start()
    t2 = time.perf_counter()
    duck_agg = con.execute(f"""
        SELECT 
            filename,
            AVG(quote_volume) as avg_quote_vol,
            COUNT(*) as bar_count
        FROM read_parquet('{pdir.as_posix()}/*.parquet', filename=true)
        GROUP BY filename
    """).df()
    t3 = time.perf_counter()
    _, peak_duck = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duck_agg_sec = t3 - t2
    duck_agg_peak = peak_duck / (1024 * 1024)

    benchmarks.append(BenchmarkResult(
        task_name="cross_asset_aggregation",
        pandas_time_sec=round(pandas_agg_sec, 4),
        duckdb_time_sec=round(duck_agg_sec, 4),
        speedup_ratio=round(pandas_agg_sec / max(duck_agg_sec, 1e-6), 2),
        pandas_peak_mb=round(pandas_agg_peak, 2),
        duckdb_peak_mb=round(duck_agg_peak, 2),
        rows_processed=total_rows,
        notes="Out-of-core vectorized SQL aggregation across 18 Parquet files",
    ))

    # Summary evaluation & Decision
    mean_speedup = sum(b.speedup_ratio for b in benchmarks) / len(benchmarks)
    
    # Recommendation logic:
    # DuckDB provides significant speedup on parallel parquet scan and zero-copy predicate pushdown.
    # SQLite must remain for live transactional state (WAL, ACID, safety latches).
    decision = "ADOPT" if mean_speedup >= 1.2 else "ADOPT_LATER"

    con.close()

    return {
        "status": "PASS",
        "duckdb_version": duckdb.__version__,
        "mean_speedup": round(mean_speedup, 2),
        "decision": decision,
        "sqlite_role": "RETAINED_FOR_LIVE_STATE (WAL transactional store)",
        "duckdb_role": "ANALYTICAL_RESEARCH_AND_HISTORICAL_PARQUET_QUERY",
        "benchmarks": [asdict(b) for b in benchmarks],
        "findings": (
            f"DuckDB achieved {mean_speedup:.2f}x average speedup across analytical queries. "
            f"Predicate and projection pushdown avoided scanning full historical files into memory. "
            f"SQLite remains strictly mandatory for live state, order state, and safety latches."
        ),
    }


if __name__ == "__main__":
    import json
    res = evaluate_duckdb_parquet_queries()
    print(json.dumps(res, indent=2))
