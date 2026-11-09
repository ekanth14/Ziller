"""Automated Data Integrity Verification for Multi-Coin Klines (Phase 4.2).

Performs rigorous institutional checks on ingested Parquet klines:
1. Gaps: Detect missing hourly intervals.
2. Duplicates: Detect repeated open timestamps.
3. Ordering: Verify strictly monotonic increasing timestamps.
4. Suspicious prices: Check high/low bounds, zero/negative prices, negative volume.
5. Date range per coin: Measure span, total bars, and completeness percentage.
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("cryptoscope.research.multi_coin.data_integrity")

ONE_HOUR_MS = 3600 * 1000


def verify_symbol_integrity(parquet_path: Path) -> Dict[str, Any]:
    """Run full data integrity audit on a single symbol's Parquet file."""
    parquet_path = Path(parquet_path)
    symbol = parquet_path.stem

    if not parquet_path.is_file():
        return {
            "symbol": symbol,
            "status": "MISSING_FILE",
            "passed": False,
            "reason": f"File does not exist: {parquet_path}",
        }

    try:
        df = pd.read_parquet(parquet_path, engine="fastparquet")
    except Exception as e:
        return {
            "symbol": symbol,
            "status": "CORRUPT_PARQUET",
            "passed": False,
            "reason": str(e),
        }

    if df.empty:
        return {
            "symbol": symbol,
            "status": "EMPTY_DATA",
            "passed": False,
            "total_bars": 0,
        }

    total_bars = len(df)
    open_times = df["open_time"].to_numpy()

    # 1. Duplicates check
    duplicate_count = int(pd.Series(open_times).duplicated().sum())

    # 2. Monotonic Ordering check
    time_diffs = np.diff(open_times)
    is_monotonic = bool(np.all(time_diffs > 0))
    ordering_violations = int(np.sum(time_diffs <= 0))

    # 3. Gaps check
    # In 1h klines, consecutive bars should differ by exactly 3,600,000 ms
    gap_mask = time_diffs > ONE_HOUR_MS
    gap_count = int(np.sum(gap_mask))
    missing_bars = int(np.sum((time_diffs[gap_mask] // ONE_HOUR_MS) - 1)) if gap_count > 0 else 0
    max_gap_hours = float(np.max(time_diffs) / ONE_HOUR_MS) if len(time_diffs) > 0 else 0.0

    # 4. Suspicious Prices & Volume
    suspicious_zero_neg_price = int(np.sum(
        (df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)
    ))
    suspicious_high_low_violation = int(np.sum(df["high"] < df["low"]))
    suspicious_bar_extremes = int(np.sum(
        (df["high"] < df["open"]) | (df["high"] < df["close"]) |
        (df["low"] > df["open"]) | (df["low"] > df["close"])
    ))
    suspicious_negative_vol = int(np.sum(
        (df["volume"] < 0) | (df["quote_volume"] < 0)
    ))

    # 5. Date Range & Completeness
    start_ms = int(open_times[0])
    end_ms = int(open_times[-1])
    start_dt = datetime.datetime.fromtimestamp(start_ms / 1000, tz=datetime.timezone.utc).isoformat()
    end_dt = datetime.datetime.fromtimestamp(end_ms / 1000, tz=datetime.timezone.utc).isoformat()
    
    expected_bars = int((end_ms - start_ms) // ONE_HOUR_MS) + 1
    completeness_pct = float(round((total_bars / max(1, expected_bars)) * 100, 3))

    passed = (
        duplicate_count == 0
        and is_monotonic
        and suspicious_zero_neg_price == 0
        and suspicious_high_low_violation == 0
        and suspicious_bar_extremes == 0
        and suspicious_negative_vol == 0
        and completeness_pct >= 95.0  # Require >=95% completeness for valid production backtest data
    )

    return {
        "symbol": symbol,
        "status": "PASS" if passed else "FLAGGED",
        "passed": passed,
        "total_bars": total_bars,
        "expected_bars": expected_bars,
        "completeness_pct": completeness_pct,
        "date_range": {
            "start": start_dt,
            "end": end_dt,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_days": round((end_ms - start_ms) / (86400 * 1000), 1),
        },
        "integrity_metrics": {
            "duplicate_timestamps": duplicate_count,
            "ordering_violations": ordering_violations,
            "is_strictly_monotonic": is_monotonic,
            "gap_events": gap_count,
            "missing_bars_count": missing_bars,
            "max_gap_hours": round(max_gap_hours, 2),
            "zero_or_negative_prices": suspicious_zero_neg_price,
            "high_less_than_low": suspicious_high_low_violation,
            "extreme_envelope_violations": suspicious_bar_extremes,
            "negative_volume_bars": suspicious_negative_vol,
        }
    }


def audit_all_parquet_klines(
    directory: Path = Path("data/parquet_klines/1h"),
    report_output_path: Optional[Path] = Path("reports/PHASE_4_DATA_INTEGRITY.json"),
) -> Dict[str, Any]:
    """Audit all parquet files in directory and generate structured report."""
    directory = Path(directory)
    parquet_files = sorted(list(directory.glob("*.parquet")))
    
    symbol_results = {}
    passed_symbols = []
    flagged_symbols = []

    for pf in parquet_files:
        res = verify_symbol_integrity(pf)
        symbol_results[res["symbol"]] = res
        if res.get("passed"):
            passed_symbols.append(res["symbol"])
        else:
            flagged_symbols.append(res["symbol"])

    summary = {
        "audited_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_files_audited": len(parquet_files),
        "passed_count": len(passed_symbols),
        "flagged_count": len(flagged_symbols),
        "passed_symbols": passed_symbols,
        "flagged_symbols": flagged_symbols,
        "details": symbol_results,
    }

    if report_output_path:
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        report_output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Saved data integrity audit report to %s", report_output_path)

    return summary


if __name__ == "__main__":
    report = audit_all_parquet_klines()
    print(f"Audited {report['total_files_audited']} symbols: {report['passed_count']} PASS, {report['flagged_count']} FLAGGED")
