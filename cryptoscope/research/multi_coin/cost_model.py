"""Dynamic Market-Microstructure Cost and Slippage Model (Phase 5.2).

Replaces static flat bps with dynamic execution cost:
Slippage = Half-Spread + Market Impact (Order Size vs 24h Volume & Volatility)

Mathematical Formulation (Square-Root Law of Market Impact):
- Spread cost: S_half = Spread_bps / 2
- Instantaneous Bar Volatility: sigma = (High - Low) / Close
- Impact Slippage (bps):
    I_bps = 10,000 * eta * sigma * sqrt(OrderSize_USD / Volume_24h_USD)
  where:
    * eta = 0.15 (empirical calibration factor for Binance Spot orderbooks)
    * Floor = 1.0 bps (irreducible network/latency jitter)
- Total Slippage (bps): Slippage_bps = S_half + I_bps
- Total Execution Cost:
    Cost_USD = OrderSize_USD * (Slippage_bps / 10,000 + TakerFee)
"""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class CostModelCalibration:
    """Microstructure calibration parameters."""
    taker_fee_pct: float = 0.00075          # 0.075% Binance VIP0 with BNB deduction
    maker_fee_pct: float = 0.00020          # 0.020% maker limit order
    eta_impact_factor: float = 0.15          # Empirical market impact constant
    min_spread_bps: float = 1.5              # 1.5 bps floor for ultra-liquid BTC/ETH
    alt_spread_floor_bps: float = 5.0        # 5.0 bps floor for altcoins
    latency_jitter_bps: float = 1.0          # 1.0 bps minimum mechanical latency slippage
    apply_indian_vda_tax: bool = False       # Optional Indian tax accounting (115BBH / 194S)


@dataclass
class ExecutionResult:
    """Detailed execution cost breakdown for a simulated trade."""
    symbol: str
    side: str
    nominal_price: float
    order_size_usd: float
    quantity: float
    effective_price: float
    half_spread_bps: float
    impact_slippage_bps: float
    total_slippage_bps: float
    slippage_cost_usd: float
    exchange_fee_usd: float
    total_cost_usd: float
    total_cost_bps: float


class DynamicCostModel:
    """Evaluates dynamic slippage and fees based on real-time / bar-level liquidity."""

    def __init__(self, calibration: Optional[CostModelCalibration] = None):
        self.calib = calibration or CostModelCalibration()

    def estimate_spread_bps(
        self,
        symbol: str,
        high: float,
        low: float,
        close: float,
        measured_spread_bps: Optional[float] = None,
    ) -> float:
        """Estimates bid-ask spread in bps using measured spread or Corwin-Schultz proxy."""
        if measured_spread_bps is not None and measured_spread_bps > 0:
            return float(measured_spread_bps)

        sym = symbol.upper()
        floor = self.calib.min_spread_bps if sym in {"BTCUSDT", "ETHUSDT"} else self.calib.alt_spread_floor_bps

        if close <= 0 or high <= low:
            return floor

        # Corwin-Schultz / Parkinson high-low volatility proxy
        hl_vol = (high - low) / close
        est_bps = hl_vol * 0.08 * 10000.0  # Approx 8% of bar range corresponds to typical bid-ask
        return float(max(floor, est_bps))

    def calculate_execution(
        self,
        symbol: str,
        side: str,
        order_size_usd: float,
        price: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        volume_24h_usd: float,
        is_maker: bool = False,
        measured_spread_bps: Optional[float] = None,
        impact_multiplier: float = 1.0,
    ) -> ExecutionResult:
        """Computes exact execution price and costs for an order of size `order_size_usd`.
        
        Args:
            symbol: Trading pair
            side: "BUY" or "SELL"
            order_size_usd: Order notional in USD/USDT
            price: Mid / reference price
            bar_high: High of the current or preceding bar
            bar_low: Low of the current or preceding bar
            bar_close: Close of the current or preceding bar
            volume_24h_usd: Rolling 24-hour quote volume
            is_maker: True if executed via passive limit order
            measured_spread_bps: Optional direct book spread
            impact_multiplier: Sensitivity stress multiplier (e.g., 0.5x, 1.0x, 2.0x)
        """
        side_clean = side.upper()
        if order_size_usd <= 0 or price <= 0:
            raise ValueError(f"Invalid order size ({order_size_usd}) or price ({price})")

        # 1. Spread estimation
        spread_bps = self.estimate_spread_bps(
            symbol=symbol,
            high=bar_high,
            low=bar_low,
            close=bar_close,
            measured_spread_bps=measured_spread_bps,
        )
        half_spread_bps = spread_bps / 2.0 if not is_maker else 0.0

        # 2. Market impact calculation
        # If maker, impact is zero (passively waiting)
        if is_maker:
            impact_bps = 0.0
        else:
            # Bar volatility
            sigma = (bar_high - bar_low) / max(bar_close, 1e-8) if bar_high > bar_low else 0.005
            vol_24h = max(volume_24h_usd, 50_000.0)  # floor to prevent division by zero
            participation_ratio = order_size_usd / vol_24h

            # Square-root market impact formula
            raw_impact = (
                self.calib.eta_impact_factor
                * impact_multiplier
                * sigma
                * math.sqrt(participation_ratio)
                * 10000.0
            )
            impact_bps = max(self.calib.latency_jitter_bps, raw_impact)

        total_slippage_bps = half_spread_bps + impact_bps

        # 3. Directional price adjustment
        slippage_fraction = total_slippage_bps / 10000.0
        if side_clean == "BUY":
            effective_price = price * (1.0 + slippage_fraction)
        elif side_clean == "SELL":
            effective_price = price * (1.0 - slippage_fraction)
        else:
            raise ValueError(f"Unknown side: {side}")

        # 4. Quantity and fees
        quantity = order_size_usd / effective_price
        fee_rate = self.calib.maker_fee_pct if is_maker else self.calib.taker_fee_pct
        exchange_fee_usd = order_size_usd * fee_rate
        slippage_cost_usd = order_size_usd * slippage_fraction
        total_cost_usd = slippage_cost_usd + exchange_fee_usd
        total_cost_bps = (total_cost_usd / order_size_usd) * 10000.0

        return ExecutionResult(
            symbol=symbol.upper(),
            side=side_clean,
            nominal_price=price,
            order_size_usd=order_size_usd,
            quantity=quantity,
            effective_price=effective_price,
            half_spread_bps=round(half_spread_bps, 2),
            impact_slippage_bps=round(impact_bps, 2),
            total_slippage_bps=round(total_slippage_bps, 2),
            slippage_cost_usd=round(slippage_cost_usd, 4),
            exchange_fee_usd=round(exchange_fee_usd, 4),
            total_cost_usd=round(total_cost_usd, 4),
            total_cost_bps=round(total_cost_bps, 2),
        )

    def run_sensitivity_analysis(
        self,
        order_sizes_usd: Optional[List[float]] = None,
        multipliers: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """Runs sensitivity stress matrix across order sizes and liquidity stress multipliers."""
        sizes = order_sizes_usd or [10.0, 50.0, 100.0, 250.0, 500.0, 1000.0]
        mults = multipliers or [0.5, 1.0, 1.5, 2.0]
        
        # Test across two benchmark profiles:
        # 1. High-liquidity (BTCUSDT: $500M 24h volume, 1.5% daily range)
        # 2. Medium-liquidity Alt (SOLUSDT / NEARUSDT: $20M 24h volume, 4% daily range)
        profiles = [
            {
                "symbol": "BTCUSDT",
                "price": 80_000.0,
                "high": 80_800.0,
                "low": 79_600.0,
                "close": 80_000.0,
                "vol_24h": 500_000_000.0,
            },
            {
                "symbol": "NEARUSDT",
                "price": 5.0,
                "high": 5.15,
                "low": 4.95,
                "close": 5.0,
                "vol_24h": 20_000_000.0,
            },
        ]

        matrix = []
        for p in profiles:
            for s in sizes:
                for m in mults:
                    res = self.calculate_execution(
                        symbol=p["symbol"],
                        side="BUY",
                        order_size_usd=s,
                        price=p["price"],
                        bar_high=p["high"],
                        bar_low=p["low"],
                        bar_close=p["close"],
                        volume_24h_usd=p["vol_24h"],
                        impact_multiplier=m,
                    )
                    matrix.append({
                        "symbol": p["symbol"],
                        "order_size_usd": s,
                        "multiplier": m,
                        "spread_bps": res.half_spread_bps * 2,
                        "impact_bps": res.impact_slippage_bps,
                        "total_slippage_bps": res.total_slippage_bps,
                        "total_cost_bps": res.total_cost_bps,
                        "total_cost_usd": res.total_cost_usd,
                    })

        return matrix
