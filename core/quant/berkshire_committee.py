"""AI Berkshire Qualitative Research Committee.

Systemizes institutional value-investing methodologies (Buffett, Munger, Duan Yongping, Li Lu)
with deterministic Python Decimal financial rigor checks, inspired by xbtlin/ai-berkshire.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


class BerkshireCommittee:
    """Multi-agent investment research committee applying 4 value investing lenses."""

    def __init__(self) -> None:
        pass

    def audit_asset(self, symbol: str, data: Mapping[str, Any]) -> dict[str, Any]:
        """Perform deterministic qualitative and quantitative rigor audit on an asset."""
        if not data or "market_cap" not in data:
            return {
                "symbol": symbol,
                "rigor_passed": False,
                "composite_conviction_score": 0.0,
                "summary": "Insufficient fundamental data to conduct Berkshire audit.",
            }

        try:
            mcap = Decimal(str(data.get("market_cap", 0)))
            vol = Decimal(str(data.get("daily_volume", 0)))
            annual_fees = Decimal(str(data.get("annual_network_fees", 0)))
            active_users = Decimal(str(data.get("active_addresses", 0)))
            top_share = Decimal(str(data.get("top_holders_share_pct", 0)))
            staking_yield = Decimal(str(data.get("staking_yield_pct", 0)))
            rigor_passed = True
        except (InvalidOperation, TypeError, ValueError):
            return {
                "symbol": symbol,
                "rigor_passed": False,
                "composite_conviction_score": 0.0,
                "summary": "Numerical data validation failed under Decimal parsing.",
            }

        # 1. Duan Yongping Lens: Moat & Business Model
        # Fee capture vs Market Cap (Price-to-Sales proxy)
        ps_ratio = (mcap / annual_fees) if annual_fees > 0 else Decimal("999.0")
        if ps_ratio < Decimal("30.0") and active_users > Decimal("500000"):
            moat_grade = "WIDE"
            moat_thesis = "Dominant network effect with robust fee generation and high switching costs."
            moat_score = 85.0
        elif active_users > Decimal("200000"):
            moat_grade = "NARROW"
            moat_thesis = "Established network utility; fee capture moderate relative to market valuation."
            moat_score = 65.0
        else:
            moat_grade = "NONE"
            moat_thesis = "Weak network retention; susceptible to competitive fee compression."
            moat_score = 40.0

        duan_moat = {
            "grade": moat_grade,
            "score": moat_score,
            "thesis": moat_thesis,
            "price_to_fee_ratio": float(round(ps_ratio, 2)),
        }

        # 2. Warren Buffett Lens: Intrinsic Value & Margin of Safety
        # Cash yield / staking yield proxy
        if staking_yield > Decimal("4.0") or ps_ratio < Decimal("20.0"):
            buffett_verdict = "ATTRACTIVE"
            margin_of_safety_pct = 30.0
            buffett_score = 80.0
            buffett_thesis = "High economic earnings yield providing substantial margin of safety."
        elif ps_ratio < Decimal("50.0") or staking_yield > Decimal("2.0"):
            buffett_verdict = "FAIR"
            margin_of_safety_pct = 10.0
            buffett_score = 60.0
            buffett_thesis = "Valuation is fair relative to current economic utility."
        else:
            buffett_verdict = "EXPENSIVE"
            margin_of_safety_pct = -20.0
            buffett_score = 35.0
            buffett_thesis = "Substantial speculative premium over fundamental economic fee throughput."

        buffett_valuation = {
            "verdict": buffett_verdict,
            "score": buffett_score,
            "margin_of_safety_pct": margin_of_safety_pct,
            "thesis": buffett_thesis,
        }

        # 3. Charlie Munger Lens: Inversion & Reflexive Failure Modes
        # Volume-to-mcap turnover > 0.40 indicates extreme speculative churning
        turnover = (vol / mcap) if mcap > 0 else Decimal("0.0")
        failure_modes: list[str] = []
        if turnover > Decimal("0.35"):
            failure_modes.append("Hyperactive speculative turnover creating reflexive cascade risk.")
        if top_share > Decimal("0.40"):
            failure_modes.append("Whale concentration risking sudden unilateral liquidity drains.")
        if annual_fees <= Decimal("1000000"):
            failure_modes.append("Fee generation fails to cover network security subsidy.")

        munger_score = max(20.0, 90.0 - (len(failure_modes) * 25.0))
        munger_inversion = {
            "score": munger_score,
            "failure_modes": failure_modes if failure_modes else ["No catastrophic structural vulnerabilities detected."],
            "inversion_verdict": "ACCEPTABLE" if len(failure_modes) <= 1 else "HAZARDOUS",
        }

        # 4. Li Lu Lens: Management & Governance Integrity
        if top_share < Decimal("0.15"):
            governance_status = "DECENTRALIZED"
            governance_score = 85.0
            lilu_thesis = "Minimal concentration risk; low key-man vulnerability."
        elif top_share < Decimal("0.30"):
            governance_status = "MODERATE"
            governance_score = 65.0
            lilu_thesis = "Moderate stakeholder concentration requiring ongoing tracking."
        else:
            governance_status = "CENTRALIZED"
            governance_score = 35.0
            lilu_thesis = "High governance concentration; significant governance attack surface."

        lilu_integrity = {
            "score": governance_score,
            "governance_status": governance_status,
            "thesis": lilu_thesis,
            "top_holders_share_pct": float(top_share * 100),
        }

        composite_score = round(
            (moat_score * 0.30)
            + (buffett_score * 0.30)
            + (munger_score * 0.20)
            + (governance_score * 0.20),
            1,
        )

        return {
            "symbol": symbol,
            "rigor_passed": rigor_passed,
            "composite_conviction_score": composite_score,
            "duan_moat": duan_moat,
            "buffett_valuation": buffett_valuation,
            "munger_inversion": munger_inversion,
            "lilu_integrity": lilu_integrity,
            "summary": f"Audit complete for {symbol}. Composite Conviction Score: {composite_score}/100.",
        }
