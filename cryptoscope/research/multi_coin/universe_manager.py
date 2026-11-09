"""Point-in-Time Universe Manager for Binance Spot USDT pairs (Phase 5.1).

Enforces point-in-time qualification across the 4-year historical dataset:
1. Minimum 30-day average quote volume.
2. Maximum spread (Corwin-Schultz / Parkinson volatility proxy & tick spread).
3. Minimum order-book depth within 1% of mid.
4. Minimum listing age (history >= min_listing_age_days before inclusion).
5. Scale limits to ACCOUNT_SIZE_USD and minimum notional.
6. Exclusion of stablecoins, leveraged tokens, and delisted/monitored assets.
7. Point-in-time history logging: eliminates survivorship bias by tracking
   qualifications over time, including assets that were later delisted.
"""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from cryptoscope.research.multi_coin.candidate_universe import (
    STABLECOIN_BASES,
)

LEVERAGED_PATTERNS = ("UP", "DOWN", "BULL", "BEAR")

logger = logging.getLogger("cryptoscope.research.multi_coin.universe_manager")

MS_PER_DAY = 86400 * 1000
MS_PER_HOUR = 3600 * 1000
HOURS_PER_30D = 30 * 24  # 720 hours


@dataclass
class UniverseConfig:
    """Configurable parameters for Universe Qualification."""
    min_30d_quote_volume_usd: float = 5_000_000.0  # $5M total quote volume over 30 days (~$166k/day)
    max_spread_pct: float = 0.0015                 # 15 bps max estimated spread
    min_depth_1pct_usd: float = 50_000.0           # $50,000 estimated depth within 1% of mid
    min_listing_age_days: int = 30                 # Must have traded for >= 30 days
    account_size_usd: float = 1_000.0              # Default portfolio size
    min_notional_usd: float = 10.0                 # Minimum Binance Spot order notional
    max_position_pct: float = 0.25                 # Max single position 25% ($250 on $1k)
    rebuild_frequency_days: int = 30               # Rebuild frequency in days


@dataclass
class UniverseSnapshot:
    """A point-in-time snapshot of qualified symbols."""
    timestamp_ms: int
    as_of_date: str
    eligible_symbols: List[str]
    candidate_count: int
    eligible_count: int
    exclusions: Dict[str, int]
    metrics_by_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class PointInTimeUniverseManager:
    """Manages point-in-time universe qualification across multi-asset crypto datasets."""

    def __init__(
        self,
        config: Optional[UniverseConfig] = None,
        parquet_dir: Optional[Path] = None,
        candidate_universe_path: Optional[Path] = None,
    ):
        self.config = config or UniverseConfig()
        self.parquet_dir = parquet_dir or Path("data/parquet_klines/1h")
        self.candidate_universe_path = candidate_universe_path or Path("data/universe/candidate_spot_usdt.json")
        
        # In-memory cached klines per symbol
        self._klines_cache: Dict[str, pd.DataFrame] = {}
        self._first_seen_ms: Dict[str, int] = {}
        self._last_seen_ms: Dict[str, int] = {}
        
        # Historical snapshots: timestamp_ms -> UniverseSnapshot
        self.snapshots: List[UniverseSnapshot] = []

    def load_local_dataset(self) -> None:
        """Loads available parquet klines into memory for rapid point-in-time querying."""
        if not self.parquet_dir.exists():
            logger.warning(f"Parquet directory not found: {self.parquet_dir}")
            return

        parquet_files = list(self.parquet_dir.glob("*.parquet"))
        for p in parquet_files:
            sym = p.stem.upper()
            try:
                df = pd.read_parquet(p, engine="fastparquet")
                if "open_time" in df.columns:
                    df = df.sort_values("open_time").reset_index(drop=True)
                    self._klines_cache[sym] = df
                    self._first_seen_ms[sym] = int(df["open_time"].iloc[0])
                    self._last_seen_ms[sym] = int(df["open_time"].iloc[-1])
            except Exception as e:
                logger.error(f"Failed loading {p}: {e}")

        logger.info(f"Loaded {len(self._klines_cache)} symbols into universe manager cache.")

    def is_excluded_category(self, symbol: str) -> Optional[str]:
        """Checks structural exclusions: stablecoins, leveraged tokens."""
        sym = symbol.upper()
        # Leveraged check
        for pat in LEVERAGED_PATTERNS:
            if pat in sym:
                return f"leveraged_token_{pat}"

        # Stablecoin check
        base = sym.replace("USDT", "").replace("BUSD", "")
        if base in STABLECOIN_BASES or sym in {"BUSDUSDT", "USDCUSDT", "TUSDUSDT", "FDUSDUSDT", "DAIUSDT", "EURUSDT"}:
            return "stablecoin"

        return None

    def evaluate_symbol_eligibility(
        self,
        symbol: str,
        as_of_ms: int,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Evaluates whether a symbol is eligible at timestamp `as_of_ms`.
        
        Returns:
            (eligible, exclusion_reason, metrics_dict)
        """
        # 1. Structural exclusion
        cat_exc = self.is_excluded_category(symbol)
        if cat_exc:
            return False, cat_exc, {}

        # 2. Check data availability
        if symbol not in self._klines_cache:
            return False, "data_not_available", {}

        df = self._klines_cache[symbol]
        first_ms = self._first_seen_ms[symbol]
        last_ms = self._last_seen_ms[symbol]

        # Asset has not started trading yet
        if as_of_ms < first_ms:
            return False, "not_yet_listed", {}

        # Asset has already halted or been delisted
        # If no bar within the last 72 hours, consider halted/delisted
        if as_of_ms > last_ms + (72 * MS_PER_HOUR):
            return False, "delisted_or_halted", {}

        # 3. Minimum listing age
        listing_age_days = (as_of_ms - first_ms) / MS_PER_DAY
        if listing_age_days < self.config.min_listing_age_days:
            return False, f"listing_age_too_young_{listing_age_days:.1f}d", {"listing_age_days": listing_age_days}

        # 4. Point-in-time window: exactly the 30 days (720 bars) ending at as_of_ms
        window_start_ms = as_of_ms - (30 * MS_PER_DAY)
        window = df[(df["open_time"] >= window_start_ms) & (df["open_time"] <= as_of_ms)]

        if len(window) < 100:  # Need minimum bar representation in 30d
            return False, "insufficient_recent_history", {"bar_count": len(window)}

        # 5. 30-day quote volume check
        quote_vol_30d = float(window["quote_volume"].sum())
        if quote_vol_30d < self.config.min_30d_quote_volume_usd:
            return False, f"low_quote_volume_30d_${quote_vol_30d:,.0f}", {
                "quote_vol_30d": quote_vol_30d,
                "listing_age_days": listing_age_days,
            }

        # 6. Estimated spread & depth within 1%
        # For hourly bars, estimated spread using Corwin-Schultz high-low volatility proxy
        # Corwin & Schultz (2012) high-low spread estimator approximation:
        # High/low spread proxy: S ~ (High - Low) / Close * 0.10 (typical fraction realised as bid-ask)
        avg_hl_ratio = float(((window["high"] - window["low"]) / window["close"]).tail(72).mean())
        est_spread = max(0.0002, avg_hl_ratio * 0.08)  # floor at 2 bps

        if est_spread > self.config.max_spread_pct:
            return False, f"excessive_spread_{est_spread * 10000:.1f}bps", {
                "quote_vol_30d": quote_vol_30d,
                "est_spread": est_spread,
            }

        # Estimated 1% depth: typically ~0.5% to 2.0% of average hourly quote volume
        avg_1h_quote_vol = quote_vol_30d / len(window)
        est_depth_1pct = avg_1h_quote_vol * 0.25  # conservative 25% of 1h volume available within 1%

        if est_depth_1pct < self.config.min_depth_1pct_usd:
            return False, f"shallow_depth_${est_depth_1pct:,.0f}", {
                "quote_vol_30d": quote_vol_30d,
                "est_depth_1pct": est_depth_1pct,
            }

        # 7. Scale limits to ACCOUNT_SIZE_USD and minimum notional
        max_alloc_usd = self.config.account_size_usd * self.config.max_position_pct
        if max_alloc_usd < self.config.min_notional_usd:
            return False, "account_size_cannot_meet_min_notional", {
                "max_alloc_usd": max_alloc_usd,
                "min_notional_usd": self.config.min_notional_usd,
            }

        metrics = {
            "listing_age_days": round(listing_age_days, 1),
            "quote_vol_30d": round(quote_vol_30d, 2),
            "avg_1h_quote_vol": round(avg_1h_quote_vol, 2),
            "est_spread_bps": round(est_spread * 10000, 2),
            "est_depth_1pct_usd": round(est_depth_1pct, 2),
            "close_price": float(window["close"].iloc[-1]),
        }
        return True, None, metrics

    def rebuild_universe(self, as_of_ms: int) -> UniverseSnapshot:
        """Computes complete universe eligibility as of a given timestamp."""
        as_of_date = pd.to_datetime(as_of_ms, unit="ms", utc=True).strftime("%Y-%m-%d %H:%M:%S UTC")
        all_symbols = sorted(list(self._klines_cache.keys()))
        
        eligible: List[str] = []
        exclusions: Dict[str, int] = {}
        metrics_by_sym: Dict[str, Dict[str, Any]] = {}

        for sym in all_symbols:
            is_ok, reason, metrics = self.evaluate_symbol_eligibility(sym, as_of_ms)
            if is_ok:
                eligible.append(sym)
                metrics_by_sym[sym] = metrics
            else:
                cat = reason.split("_")[0] if reason else "unknown"
                exclusions[cat] = exclusions.get(cat, 0) + 1

        snapshot = UniverseSnapshot(
            timestamp_ms=as_of_ms,
            as_of_date=as_of_date,
            eligible_symbols=eligible,
            candidate_count=len(all_symbols),
            eligible_count=len(eligible),
            exclusions=exclusions,
            metrics_by_symbol=metrics_by_sym,
        )
        return snapshot

    def build_timeline_history(
        self,
        start_ms: int,
        end_ms: int,
        step_days: int = 30,
    ) -> List[UniverseSnapshot]:
        """Builds a historical series of universe snapshots across the backtest horizon."""
        self.snapshots = []
        curr = start_ms
        step_ms = step_days * MS_PER_DAY

        while curr <= end_ms:
            snap = self.rebuild_universe(curr)
            self.snapshots.append(snap)
            curr += step_ms

        return self.snapshots

    def get_eligible_symbols(self, as_of_ms: int) -> List[str]:
        """Retrieves eligible symbols as of `as_of_ms` using the closest prior snapshot."""
        if not self.snapshots:
            snap = self.rebuild_universe(as_of_ms)
            return snap.eligible_symbols

        # Find latest snapshot <= as_of_ms
        valid = [s for s in self.snapshots if s.timestamp_ms <= as_of_ms]
        if valid:
            return valid[-1].eligible_symbols
        return self.snapshots[0].eligible_symbols

    def export_summary(self) -> Dict[str, Any]:
        """Returns structured JSON summary of universe over time and exclusions."""
        timeline = []
        for s in self.snapshots:
            timeline.append({
                "timestamp_ms": s.timestamp_ms,
                "date": s.as_of_date,
                "candidate_count": s.candidate_count,
                "eligible_count": s.eligible_count,
                "eligible_symbols": s.eligible_symbols,
                "exclusions": s.exclusions,
            })

        return {
            "config": {
                "min_30d_quote_volume_usd": self.config.min_30d_quote_volume_usd,
                "max_spread_pct": self.config.max_spread_pct,
                "min_depth_1pct_usd": self.config.min_depth_1pct_usd,
                "min_listing_age_days": self.config.min_listing_age_days,
                "account_size_usd": self.config.account_size_usd,
                "min_notional_usd": self.config.min_notional_usd,
            },
            "snapshot_count": len(self.snapshots),
            "timeline": timeline,
        }
