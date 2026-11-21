"""Indicator catalog: every pandas-ta-classic indicator as a no-lookahead feature per coin/timeframe.

Each feature value at bar t uses only bars 0..t (the bar's own close included), so it can be used to
decide on bar t's close and trade at bar t+1's open. `audit_lookahead` proves it: it recomputes the
catalog on truncated histories and checks that no earlier value changes when later bars are removed.

Excluded (and why):
  math category   element-wise helpers (sin, log10, add ...), not indicators
  dpo             centred by default: the value at t uses bars after t
  tos_stdevall    one regression fitted over the whole series: every value sees the future
  vp              volume profile: price bins, not a per-bar series
  mavp, beta, correl, long_run, short_run, tsignals, xsignals
                  need extra inputs (a period series, a benchmark, or other indicators)
  ICS_* column    Ichimoku chikou span is the close shifted 26 bars back, i.e. a future price
"""
from __future__ import annotations

import warnings
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

try:  # optional at import time so the dashboard still loads without it
    import pandas_ta_classic as ta
except ImportError:  # pragma: no cover - reported by catalog_summary
    ta = None

SKIP_CATEGORIES = {"math"}
EXCLUDED: Dict[str, str] = {
    "dpo": "centred: uses bars after t",
    "tos_stdevall": "whole-series regression: sees the future",
    "vp": "volume profile bins, not a per-bar series",
    "mavp": "needs a period series",
    "beta": "needs a benchmark series",
    "correl": "needs a benchmark series",
    "long_run": "needs fast/slow inputs",
    "short_run": "needs fast/slow inputs",
    "tsignals": "needs a trend input",
    "xsignals": "needs signal/threshold inputs",
}
EXCLUDED_COLUMN_PREFIXES = {"ICS_": "Ichimoku chikou span = close 26 bars later (future price)"}


def available() -> bool:
    return ta is not None


def candles_frame(candles: Sequence[Dict[str, float]]) -> pd.DataFrame:
    """OHLCV DataFrame with a UTC DatetimeIndex (anchored indicators such as VWAP need one)."""
    df = pd.DataFrame([{k: float(b[k]) for k in ("open", "high", "low", "close", "volume")} for b in candles])
    df.index = pd.to_datetime([float(b["open_time"]) for b in candles], unit="s", utc=True)
    return df


def indicator_names() -> List[str]:
    if ta is None:
        return []
    return [n for cat, names in ta.Category.items() if cat not in SKIP_CATEGORIES
            for n in names if n not in EXCLUDED]


def _category_of() -> Dict[str, str]:
    return {n: cat for cat, names in (ta.Category.items() if ta else []) for n in names}


def compute_catalog(candles: Sequence[Dict[str, float]], names: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """All catalog features (columns) for the candles (rows). Indicators that fail are skipped."""
    if ta is None:
        raise RuntimeError("pandas-ta-classic is not installed")
    df = candles_frame(candles)
    cols: Dict[str, pd.Series] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with np.errstate(all="ignore"):
            for name in (names or indicator_names()):
                try:
                    out = getattr(df.ta, name)()
                except Exception:  # noqa: BLE001 - one broken indicator never takes the catalog down
                    continue
                if isinstance(out, tuple):        # ichimoku returns (lines, forward span)
                    out = out[0]
                if isinstance(out, pd.Series):
                    out = out.to_frame(out.name or name)
                if not isinstance(out, pd.DataFrame) or len(out) != len(df):
                    continue
                for col in out.columns:
                    key = str(col)
                    if key in cols or any(key.startswith(p) for p in EXCLUDED_COLUMN_PREFIXES):
                        continue
                    s = pd.to_numeric(out[col], errors="coerce").astype(float)
                    if s.notna().any():
                        cols[key] = s.reindex(df.index)
    feats = pd.DataFrame(cols, index=df.index)
    return feats.replace([np.inf, -np.inf], np.nan)


def audit_lookahead(candles: Sequence[Dict[str, float]], cuts: Sequence[int],
                    names: Optional[Iterable[str]] = None, rtol: float = 1e-7) -> Dict[str, int]:
    """Columns whose value at some bar < cut changes when bars >= cut are removed -> first bad cut."""
    names = list(names or indicator_names())
    full = compute_catalog(candles, names)
    bad: Dict[str, int] = {}
    for cut in cuts:
        part = compute_catalog(candles[:cut], names)
        a = full.iloc[:cut].reindex(columns=part.columns).to_numpy(float)
        b = part.to_numpy(float)
        diff = ~np.isclose(a, b, rtol=rtol, atol=1e-10, equal_nan=True)
        for col, hit in zip(part.columns, diff.any(axis=0)):
            if hit:
                bad.setdefault(col, cut)
        for col in set(full.columns) - set(part.columns):
            if full[col].iloc[:cut].notna().any():   # a value existed only because later bars did
                bad.setdefault(col, cut)
    return bad


def catalog_summary(feats: Optional[pd.DataFrame]) -> Dict[str, object]:
    """Counts per category, the excluded list, and each feature's latest value (for the Lab page)."""
    if ta is None:
        return {"status": "UNAVAILABLE", "error": "pandas-ta-classic not installed"}
    if feats is None or feats.empty:
        return {"status": "EMPTY"}
    cat = _category_of()
    per_cat: Dict[str, int] = {}
    for name in indicator_names():
        per_cat[cat.get(name, "other")] = per_cat.get(cat.get(name, "other"), 0) + 1
    last = feats.iloc[-1]
    latest = {k: (None if pd.isna(v) else round(float(v), 6)) for k, v in last.items()}
    return {"status": "OK", "library": f"pandas-ta-classic {getattr(ta, 'version', '')}".strip(),
            "indicators": len(indicator_names()), "features": int(feats.shape[1]), "per_category": per_cat,
            "excluded": {**EXCLUDED, **{p + "*": why for p, why in EXCLUDED_COLUMN_PREFIXES.items()},
                         "math category": "element-wise helpers, not indicators"},
            "latest": latest}
