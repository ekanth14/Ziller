"""Accountant Trade Ledger Exporter (Phase 7.3).

Generates formal CSV audit records for Virtual Digital Asset (VDA) transactions:
- Columns: Timestamp (UTC), Symbol, Side, Quantity, Execution Price (USDT),
  Fee (USDT), Realized PnL (USDT), USD/INR Rate, Realized PnL (INR), Order ID, Execution Type.
- Integrates with FxRateService to fetch real-time or historical USD/INR conversion.
- Statutory Disclaimer: Strictly reports factual trade execution and FX conversion
  without providing tax advice.
"""

import csv
import datetime
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptoscope.fx.rate_service import FxRateService

logger = logging.getLogger("cryptoscope.research.multi_coin.trade_ledger")

ACCOUNTANT_DISCLAIMER = (
    "# DISCLAIMER: Prepared for accountant review under Virtual Digital Asset (VDA) "
    "transaction accounting. No tax advice is provided in this export."
)


class AccountantTradeLedger:
    """Manages trade accounting and formal CSV exports for external accountants."""

    def __init__(self, fx_service: Optional[FxRateService] = None, fallback_usd_inr: float = 84.50):
        self.fx_service = fx_service or FxRateService()
        self.fallback_usd_inr = fallback_usd_inr
        self.entries: List[Dict[str, Any]] = []

    def get_current_usd_inr_rate(self) -> float:
        """Retrieves point-in-time USD/INR rate from FX service with fallback."""
        try:
            rate_info = self.fx_service.get_rate("INR", auto_fetch=True)
            if rate_info.get("status") in {"available", "stale"} and rate_info.get("rate"):
                return float(rate_info["rate"])
        except Exception as e:
            logger.warning("FX rate service lookup failed: %s; using reference fallback", e)
        return self.fallback_usd_inr

    def record_entry(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price_usdt: float,
        fee_usdt: float,
        realized_pnl_usdt: float,
        order_id: str,
        execution_type: str = "MARKET",
        timestamp_utc: Optional[str] = None,
        usd_inr_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Records a single executed trade into the ledger."""
        ts = timestamp_utc or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rate = usd_inr_rate if (usd_inr_rate is not None and usd_inr_rate > 0) else self.get_current_usd_inr_rate()
        
        realized_pnl_inr = realized_pnl_usdt * rate
        fee_inr = fee_usdt * rate

        entry = {
            "timestamp_utc": ts,
            "symbol": symbol.upper(),
            "side": side.upper(),
            "quantity": round(quantity, 8),
            "price_usdt": round(price_usdt, 4),
            "fee_usdt": round(fee_usdt, 4),
            "realized_pnl_usdt": round(realized_pnl_usdt, 4),
            "usd_inr_rate": round(rate, 2),
            "realized_pnl_inr": round(realized_pnl_inr, 2),
            "fee_inr": round(fee_inr, 2),
            "order_id": str(order_id),
            "execution_type": execution_type.upper(),
        }
        self.entries.append(entry)
        return entry

    def export_csv(self, output_path: Optional[Path] = None) -> str:
        """Exports recorded ledger entries to formatted CSV string or file."""
        output = io.StringIO()
        # Add accountant disclaimer at top
        output.write(ACCOUNTANT_DISCLAIMER + "\n")
        
        fieldnames = [
            "timestamp_utc",
            "symbol",
            "side",
            "quantity",
            "price_usdt",
            "fee_usdt",
            "realized_pnl_usdt",
            "usd_inr_rate",
            "realized_pnl_inr",
            "fee_inr",
            "order_id",
            "execution_type",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for e in self.entries:
            writer.writerow(e)

        csv_content = output.getvalue()
        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(csv_content)
            logger.info("Saved accountant trade ledger to %s", p)

        return csv_content
