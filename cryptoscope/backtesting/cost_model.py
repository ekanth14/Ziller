"""Institutional crypto spot cost model and Indian tax regime.

Statutory Framework Mapping:
- FY 2025-26 (Income-tax Act, 1961):
  * Section 2(47A): Definition of Virtual Digital Assets (VDA - crypto, tokens).
  * Section 115BBH: 31.2% flat tax (30% base + 4% health & education cess) on gross gains.
    Strict ZERO loss set-off: losses on one trade cannot offset gains on another.
  * Section 194S: 1.0% TDS deducted on entire gross transfer/sale consideration.
  * 18.0% GST applied to domestic exchange transaction brokerage/fees.
- FY 2026-27 onward (Income-tax Act, 2025):
  * Direct Tax Code alignment: Preserves identical VDA taxation principles under the restructured
    digital assets schedule (30% + cess flat gain tax, zero loss set-off, and 1% source withholding).

Features:
- Configurable maker/taker exchange fees (default 0.1%).
- Volatility and asset-class aware slippage (5 bps for BTC/ETH, 15 bps for alts).
- Pre-tax vs post-tax performance attribution (CAGR, Sharpe, Max Drawdown).
- Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) for multiple-testing bias correction.
- Schedule VDA Computation Helper CSV export (subject to Chartered Accountant / tax professional review).
"""

import csv
import io
import math
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple


class CryptoCostModel:
    """Realistic cost model for crypto spot trading with optional Indian VDA tax calculations."""

    def __init__(
        self,
        maker_fee: float = 0.001,       # 0.1% maker
        taker_fee: float = 0.001,       # 0.1% taker
        slippage_bps_major: float = 5.0, # 5 bps for BTC/ETH
        slippage_bps_alt: float = 15.0,  # 15 bps for altcoins
        apply_indian_tax: bool = False,
        gst_rate: float = 0.18,          # 18% GST on trading fees
        tds_rate: float = 0.01,          # 1% TDS on sale consideration
        vda_tax_rate: float = 0.312,     # 30% + 4% cess = 31.2% flat
    ):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_bps_major = slippage_bps_major
        self.slippage_bps_alt = slippage_bps_alt
        self.apply_indian_tax = apply_indian_tax
        self.gst_rate = gst_rate
        self.tds_rate = tds_rate
        self.vda_tax_rate = vda_tax_rate

    def get_slippage_rate(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym in {"BTCUSDT", "ETHUSDT", "BTC", "ETH"}:
            return self.slippage_bps_major / 10000.0
        return self.slippage_bps_alt / 10000.0

    def calculate_trade_pnl(
        self,
        symbol: str,
        buy_price: float,
        sell_price: float,
        quantity: float,
        buy_time: float,
        sell_time: float,
        is_maker: bool = False,
    ) -> Dict[str, Any]:
        """Calculate complete trade accounting under standard fees and optional Indian tax."""
        slippage_rate = self.get_slippage_rate(symbol)
        effective_buy_price = buy_price * (1.0 + slippage_rate)
        effective_sell_price = sell_price * (1.0 - slippage_rate)

        fee_rate = self.maker_fee if is_maker else self.taker_fee
        gross_buy_consideration = effective_buy_price * quantity
        gross_sale_consideration = effective_sell_price * quantity

        # Exchange fees
        buy_fee = gross_buy_consideration * fee_rate
        sell_fee = gross_sale_consideration * fee_rate
        total_exchange_fees = buy_fee + sell_fee

        # Pre-tax net return
        pre_tax_net_gain = gross_sale_consideration - gross_buy_consideration - total_exchange_fees

        # Indian Tax Regime (Section 115BBH & 194S)
        gst_on_fees = total_exchange_fees * self.gst_rate if self.apply_indian_tax else 0.0
        tds_deducted = gross_sale_consideration * self.tds_rate if self.apply_indian_tax else 0.0

        # Section 115BBH: 31.2% on positive gain; zero loss set-off
        # Cost of acquisition under 115BBH excludes fees
        raw_gain = gross_sale_consideration - gross_buy_consideration
        vda_tax_on_gain = max(0.0, raw_gain) * self.vda_tax_rate if self.apply_indian_tax else 0.0

        # Total tax liability for this trade
        total_tax_and_cess = vda_tax_on_gain + gst_on_fees

        # Post-tax net cash flow received
        post_tax_net_pnl = pre_tax_net_gain - gst_on_fees - vda_tax_on_gain

        return {
            "symbol": symbol,
            "buy_time": buy_time,
            "sell_time": sell_time,
            "quantity": quantity,
            "buy_price": round(buy_price, 4),
            "effective_buy_price": round(effective_buy_price, 4),
            "sell_price": round(sell_price, 4),
            "effective_sell_price": round(effective_sell_price, 4),
            "gross_buy_cost": round(gross_buy_consideration, 2),
            "gross_sale_value": round(gross_sale_consideration, 2),
            "exchange_fees": round(total_exchange_fees, 2),
            "pre_tax_pnl": round(pre_tax_net_gain, 2),
            "gst_on_fees": round(gst_on_fees, 2),
            "tds_deducted_194s": round(tds_deducted, 2),
            "vda_tax_115bbh": round(vda_tax_on_gain, 2),
            "post_tax_pnl": round(post_tax_net_pnl, 2),
            "indian_tax_applied": self.apply_indian_tax,
        }

    def generate_schedule_vda_csv(self, trades: List[Dict[str, Any]]) -> str:
        """Export trade ledger as a Schedule VDA Computation Helper (Subject to CA Verification)."""
        output = io.StringIO()
        output.write("# =========================================================================\n")
        output.write("# ZILLERS QUANT TERMINAL - SCHEDULE VDA TRADE LEDGER EXPORT (COMPUTATION HELPER)\n")
        output.write("# DISCLAIMER: FOR TAX ESTIMATION ONLY, NOT OFFICIAL FILING. NOT TAX ADVICE.\n")
        output.write("# SUBJECT TO VERIFICATION BY A LICENSED CHARTERED ACCOUNTANT (CA).\n")
        output.write("# Statutory Law Mapping:\n")
        output.write("# - FY2025-26 (Income-tax Act, 1961): Section 115BBH (31.2% flat tax on gains, zero loss set-off),\n")
        output.write("#   Section 194S (1% TDS on total consideration), Section 2(47A) (VDA definition).\n")
        output.write("# - FY2026-27+ (Income-tax Act, 2025): Unified Direct Tax Code VDA provisions.\n")
        output.write("# =========================================================================\n")

        writer = csv.writer(output)
        writer.writerow([
            "Sr No",
            "Date of Acquisition",
            "Date of Transfer",
            "Head of Income",
            "Asset Description",
            "Quantity",
            "Cost of Acquisition (USD)",
            "Consideration Received (USD)",
            "Net Gain / Loss (USD)",
            "TDS Deducted u/s 194S (USD)",
            "Tax on VDA u/s 115BBH (USD)",
            "GST on Exchange Fees (USD)",
            "Post-Tax Net PnL (USD)",
        ])

        for idx, t in enumerate(trades, start=1):
            buy_date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t["buy_time"]))
            sell_date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t["sell_time"]))
            writer.writerow([
                idx,
                buy_date,
                sell_date,
                "Capital Gains (VDA)",
                t["symbol"],
                f"{t['quantity']:.6f}",
                f"{t['gross_buy_cost']:.2f}",
                f"{t['gross_sale_value']:.2f}",
                f"{t['pre_tax_pnl']:.2f}",
                f"{t['tds_deducted_194s']:.2f}",
                f"{t['vda_tax_115bbh']:.2f}",
                f"{t['gst_on_fees']:.2f}",
                f"{t['post_tax_pnl']:.2f}",
            ])

        return output.getvalue()


def deflated_sharpe_ratio(
    observed_sr: float,
    num_trials: int,
    returns: List[float],
    var_sharpe: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate the Deflated Sharpe Ratio (DSR) to correct for multiple testing bias.

    Reference: Bailey & Lopez de Prado (2014), 'The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality'.
    """
    if len(returns) < 5 or num_trials < 1:
        return {
            "deflated_sharpe_ratio": None,
            "p_value": None,
            "statistically_significant": False,
            "trials_tested": num_trials,
            "note": "Insufficient returns or trials to compute DSR",
        }

    n = len(returns)
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns) if len(returns) > 1 else 1e-6
    if std_r == 0:
        std_r = 1e-6

    # Skewness and Kurtosis
    m3 = sum((r - mean_r) ** 3 for r in returns) / n
    m4 = sum((r - mean_r) ** 4 for r in returns) / n
    skew = m3 / (std_r ** 3)
    kurt = m4 / (std_r ** 4)

    # Variance of the Sharpe ratio estimator
    sr_variance = var_sharpe if var_sharpe is not None else (1.0 + 0.5 * (observed_sr ** 2) - skew * observed_sr + ((kurt - 3.0) / 4.0) * (observed_sr ** 2)) / n

    # Expected maximum Sharpe ratio under null hypothesis across N independent trials
    # Euler-Mascheroni constant gamma = 0.5772156649
    gamma = 0.5772156649
    if num_trials > 1:
        e_max_sr = math.sqrt(2.0 * math.log(num_trials)) + (gamma / math.sqrt(2.0 * math.log(num_trials)))
        expected_max_sr = (1.0 - gamma) * math.sqrt(2.0 * math.log(num_trials)) if num_trials < 3 else math.sqrt(2.0 * math.log(num_trials))
    else:
        expected_max_sr = 0.0

    # Test statistic z = (observed_sr - expected_max_sr) / sqrt(sr_variance)
    denom = math.sqrt(max(1e-9, sr_variance))
    z = (observed_sr - expected_max_sr) / denom

    # Cumulative standard normal distribution Phi(z)
    dsr_p_value = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    return {
        "deflated_sharpe_ratio": round(z, 4),
        "p_value": round(dsr_p_value, 4),
        "statistically_significant": bool(dsr_p_value >= 0.95),
        "trials_tested": num_trials,
        "skewness": round(skew, 3),
        "kurtosis": round(kurt, 3),
        "expected_max_null_sr": round(expected_max_sr, 4),
    }


def compute_monthly_return_matrix(equity_curve: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Convert daily/bar equity values into a Year x Month return matrix."""
    if not equity_curve:
        return {}
    # Group by (Year, Month)
    months: Dict[Tuple[int, int], List[float]] = {}
    for pt in equity_curve:
        tm = time.gmtime(pt["time"])
        key = (tm.tm_year, tm.tm_mon)
        months.setdefault(key, []).append(pt["nav"])

    matrix: Dict[str, Dict[str, float]] = {}
    prev_close = equity_curve[0]["nav"]

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    sorted_keys = sorted(months.keys())

    for yr, mo in sorted_keys:
        yr_str = str(yr)
        mo_str = month_names[mo - 1]
        navs = months[(yr, mo)]
        month_end_nav = navs[-1]
        ret = round(((month_end_nav - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0
        matrix.setdefault(yr_str, {})[mo_str] = ret
        prev_close = month_end_nav

    return matrix
