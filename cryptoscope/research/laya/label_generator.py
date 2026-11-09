"""Triple-Barrier Labeling & Zero-Lookahead Feature Serialization (Phase 8.2).

Generates grounded training targets and compact feature representations:
1. Triple-Barrier Targets (BUY / SELL / HOLD):
   - Upper Barrier: +k * ATR_14 (scaled for Phase 5 execution costs).
   - Lower Barrier: -k * ATR_14.
   - Horizon Barrier: H = 24 hourly bars.
   - Label 1 = BUY, Label 2 = SELL, Label 0 = HOLD.
2. Zero-Lookahead Features (< 128 tokens):
   - Only data available up to closed bar t is used.
   - Outputs both numeric feature vector (for GBDT / linear baselines)
     and compact text template (< 128 tokens) for ModernBERT.
"""

from dataclasses import dataclass
import datetime
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


LABEL_HOLD = 0
LABEL_BUY = 1
LABEL_SELL = 2
LABEL_NAMES = {LABEL_HOLD: "HOLD", LABEL_BUY: "BUY", LABEL_SELL: "SELL"}


@dataclass
class DatasetMetrics:
    """Summary of extracted labels and class balance."""
    total_samples: int
    hold_count: int
    buy_count: int
    sell_count: int
    hold_pct: float
    buy_pct: float
    sell_pct: float


def compute_triple_barrier_labels(
    df: pd.DataFrame,
    horizon_bars: int = 24,
    atr_multiple: float = 1.5,
    min_barrier_pct: float = 0.015,  # 1.5% min barrier
    roundtrip_cost_pct: float = 0.0025,  # 25 bps roundtrip cost from Phase 5 model
) -> Tuple[np.ndarray, DatasetMetrics]:
    """Computes triple-barrier labels across full historical dataframe."""
    n = len(df)
    labels = np.zeros(n, dtype=int)
    
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    
    # Calculate ATR 14
    prev_closes = np.roll(closes, 1)
    prev_closes[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_closes), np.abs(lows - prev_closes)))
    atr_14 = pd.Series(tr).rolling(14).mean().fillna(tr[0]).values
    atr_pct = atr_14 / np.maximum(closes, 1e-8)

    for i in range(n):
        # We need horizon lookahead for ground truth labels
        if i + horizon_bars >= n:
            labels[i] = LABEL_HOLD
            continue

        c0 = closes[i]
        barrier_delta = max(min_barrier_pct, atr_multiple * atr_pct[i])
        upper_target = c0 * (1.0 + barrier_delta + roundtrip_cost_pct)
        lower_target = c0 * (1.0 - barrier_delta - roundtrip_cost_pct)

        # Inspect subsequent H bars
        future_highs = highs[i + 1 : i + 1 + horizon_bars]
        future_lows = lows[i + 1 : i + 1 + horizon_bars]

        first_touch = LABEL_HOLD
        for step in range(len(future_highs)):
            h = future_highs[step]
            l = future_lows[step]

            hit_upper = h >= upper_target
            hit_lower = l <= lower_target

            if hit_upper and not hit_lower:
                first_touch = LABEL_BUY
                break
            elif hit_lower and not hit_upper:
                first_touch = LABEL_SELL
                break
            elif hit_upper and hit_lower:
                # Both hit in same bar -> ambiguous, assign HOLD to be conservative
                first_touch = LABEL_HOLD
                break

        labels[i] = first_touch

    # Metrics
    valid_labels = labels[: n - horizon_bars]
    total = len(valid_labels) if len(valid_labels) > 0 else 1
    h_cnt = int(np.sum(valid_labels == LABEL_HOLD))
    b_cnt = int(np.sum(valid_labels == LABEL_BUY))
    s_cnt = int(np.sum(valid_labels == LABEL_SELL))

    metrics = DatasetMetrics(
        total_samples=total,
        hold_count=h_cnt,
        buy_count=b_cnt,
        sell_count=s_cnt,
        hold_pct=round((h_cnt / total) * 100.0, 2),
        buy_pct=round((b_cnt / total) * 100.0, 2),
        sell_pct=round((s_cnt / total) * 100.0, 2),
    )
    return labels, metrics


def extract_features_at_bar(
    df: pd.DataFrame,
    idx: int,
    symbol: str = "BTCUSDT",
) -> Tuple[np.ndarray, str]:
    """Extracts numeric feature vector and compact text template strictly at bar `idx`.
    
    Zero lookahead guarantee: relies only on df.iloc[:idx+1].
    """
    if idx < 55:
        # Pad with zeros if insufficient warmup
        return np.zeros(12, dtype=np.float32), f"sym={symbol} warmup"

    closes = df["close"].iloc[idx - 50 : idx + 1].values
    volumes = df["volume"].iloc[idx - 20 : idx + 1].values
    highs = df["high"].iloc[idx - 20 : idx + 1].values
    lows = df["low"].iloc[idx - 20 : idx + 1].values
    
    c = closes[-1]
    
    # 1. Returns
    ret_1h = (c - closes[-2]) / closes[-2]
    ret_4h = (c - closes[-5]) / closes[-5] if len(closes) >= 5 else 0.0
    ret_24h = (c - closes[-25]) / closes[-25] if len(closes) >= 25 else 0.0
    ret_7d = (c - closes[0]) / closes[0]

    # 2. RSI 14
    deltas = np.diff(closes[-15:])
    g = np.maximum(deltas, 0)
    l = np.maximum(-deltas, 0)
    avg_g = np.mean(g)
    avg_l = np.mean(l)
    rsi_14 = 50.0 if avg_l == 0 else float(100.0 - (100.0 / (1.0 + (avg_g / avg_l))))

    # 3. EMA Relationships
    c_series = pd.Series(closes)
    ema20 = float(c_series.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(c_series.ewm(span=50, adjust=False).mean().iloc[-1])
    ema20_ratio = (c - ema20) / ema20
    ema50_ratio = (c - ema50) / ema50

    # 4. Volatility & ATR %
    hl_range = (highs[-1] - lows[-1]) / c
    atr_pct = float(np.mean((highs - lows) / closes[-len(highs):]))

    # 5. Volume Ratio & Delta Direction
    vol_sma = np.mean(volumes[:-1]) if len(volumes) > 1 else 1.0
    vol_ratio = volumes[-1] / max(vol_sma, 1e-6)
    
    # Taker volume proxy (CVD delta direction)
    cvd_dir = 1.0 if c >= df["open"].iloc[idx] else -1.0

    # 6. Price Z-Score over 20 bars
    recent_closes = closes[-20:]
    std_20 = np.std(recent_closes)
    z_score_20 = float((c - np.mean(recent_closes)) / max(std_20, 1e-6))

    # 7. Regime Tag
    if ema20 > ema50 and c > ema20:
        regime = "BULL_TREND"
    elif ema20 < ema50 and c < ema20:
        regime = "BEAR_TREND"
    else:
        regime = "CONSOLIDATION"

    # Numeric vector (12 features)
    vec = np.array([
        ret_1h,
        ret_4h,
        ret_24h,
        ret_7d,
        rsi_14 / 100.0,
        ema20_ratio,
        ema50_ratio,
        hl_range,
        atr_pct,
        min(vol_ratio, 10.0) / 10.0,
        cvd_dir,
        max(-3.0, min(3.0, z_score_20)) / 3.0,
    ], dtype=np.float32)

    # Compact text serialization (< 128 tokens)
    ts_val = int(df["open_time"].iloc[idx])
    text = (
        f"sym={symbol} ts={ts_val} r1h={ret_1h*100:+.2f}% r24h={ret_24h*100:+.2f}% "
        f"rsi={rsi_14:.1f} ema20={ema20_ratio*100:+.2f}% atr={atr_pct*100:.2f}% "
        f"vol_r={vol_ratio:.1f} cvd={int(cvd_dir)} z={z_score_20:.2f} reg={regime}"
    )

    return vec, text


def verify_no_lookahead(df: pd.DataFrame, test_idx: int) -> bool:
    """Rigorous assertion proving zero lookahead in feature extraction."""
    # 1. Extract using full dataset
    vec_full, txt_full = extract_features_at_bar(df, test_idx)
    
    # 2. Slice dataframe strictly at test_idx (drop all future rows)
    df_sliced = df.iloc[: test_idx + 1].copy()
    vec_sliced, txt_sliced = extract_features_at_bar(df_sliced, test_idx)
    
    # Must be bit-for-bit identical
    assert np.allclose(vec_full, vec_sliced, rtol=1e-6, atol=1e-6)
    assert txt_full == txt_sliced
    return True
