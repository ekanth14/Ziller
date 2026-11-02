"""Constant-product AMM liquidity impact and sell scenario calculations.

Adapted from QuantOrb on-chain rules.
Models exact price drop when supply from linked, fresh, or insider-transferred wallets is dumped
into constant-product decentralized exchange liquidity pools.
"""
import math
from typing import Any, Dict, List, Optional


def constant_product_impact(q: float, R: float) -> float:
    """Calculate price drop fraction when q tokens are sold into a constant-product pool

    holding R reserve tokens. Formula: 1 - (R / (R + q))^2.
    """
    if q <= 0 or R <= 0:
        return 0.0
    ratio = R / (R + q)
    return max(0.0, min(1.0, 1.0 - (ratio * ratio)))


def calculate_sell_scenario(
    holders: List[Dict[str, Any]],
    operators: List[Dict[str, Any]],
    float_tokens: float,
    reserve_tokens: float,
) -> Optional[Dict[str, Any]]:
    """Compute catastrophic dump scenario if linked, virgin, or transfer wallets sell."""
    if float_tokens <= 0 or reserve_tokens <= 0:
        return None

    real_operators = [op for op in operators if len(op.get("wallets", [])) > 1]
    real_ids = {op["id"] for op in real_operators if op.get("id")}

    suspicious_holders = []
    for h in holders:
        is_linked = bool(h.get("op") and h.get("op") in real_ids)
        is_transfer = h.get("kind") == "transfer"
        is_virgin = bool(h.get("virgin"))
        is_sniper_holding = bool(h.get("sniper") and not h.get("sold"))
        is_bundle = bool(h.get("bundle") and not h.get("sold"))

        if is_linked or is_transfer or is_virgin or is_sniper_holding or is_bundle:
            suspicious_holders.append(h)

    if not suspicious_holders:
        return None

    q_share = sum(float(h.get("share", 0.0)) for h in suspicious_holders)
    q_tokens = q_share * float_tokens
    price_drop = constant_product_impact(q_tokens, reserve_tokens)

    # Only report scenario if price drop >= 40% (0.40)
    if price_drop < 0.40:
        return None

    linked_share = sum(float(h.get("share", 0.0)) for h in suspicious_holders if h.get("op") and h.get("op") in real_ids)
    fresh_share = sum(float(h.get("share", 0.0)) for h in suspicious_holders if not (h.get("op") and h.get("op") in real_ids) and h.get("virgin"))
    transfer_share = sum(
        float(h.get("share", 0.0))
        for h in suspicious_holders
        if not (h.get("op") and h.get("op") in real_ids) and not h.get("virgin") and h.get("kind") == "transfer"
    )

    return {
        "price_drop_pct": round(price_drop * 100.0, 2),
        "total_dump_share_pct": round(q_share * 100.0, 2),
        "suspect_wallets_count": len(suspicious_holders),
        "breakdown": {
            "linked_operators_share_pct": round(linked_share * 100.0, 2),
            "fresh_virgin_share_pct": round(fresh_share * 100.0, 2),
            "unbought_transfer_share_pct": round(transfer_share * 100.0, 2),
        },
    }
