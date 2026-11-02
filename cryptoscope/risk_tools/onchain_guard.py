"""On-chain token safety scoring, operator wallet clustering, and rugpull guard.

Faithfully adapted from QuantOrb's open on-chain rules specification.
Scores tokens from 0 to 100 with categorical bands: CLEAN, OK, RISKY, DANGER.
"""
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptoscope.risk_tools.amm_impact import calculate_sell_scenario, constant_product_impact

WEIGHTS = {
    "operator": 35.0,
    "virgin": 25.0,
    "transfer": 20.0,
    "sniper": 10.0,
    "concentration": 10.0,
}

SCALE = {
    "operator": (0.10, 0.60),
    "virgin": (0.10, 0.80),
    "transfer": (0.01, 0.10),
    "sniper": (0.01, 0.15),
    "concentration": (0.25, 0.70),
}


def _linear_part(key: str, value: float) -> float:
    """Calculate weighted linear contribution for a metric."""
    good, bad = SCALE[key]
    if value <= good:
        q = 1.0
    elif value >= bad:
        q = 0.0
    else:
        q = (bad - value) / (bad - good)
    return round(WEIGHTS[key] * q, 1)


class DisjointSet:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: int, j: int):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def cluster_operators(
    holders: List[Dict[str, Any]],
    links: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Cluster individual holder wallets into unified operators based on proven on-chain links

    and coordinated wallet packs.
    """
    n = len(holders)
    if n == 0:
        return []

    dsu = DisjointSet(n)
    links = links or []

    # 1. Merge proven links
    for l in links:
        if l.get("level") == "proven":
            a = int(l.get("a", 0))
            b = int(l.get("b", 0))
            if 0 <= a < n and 0 <= b < n:
                dsu.union(a, b)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        root = dsu.find(i)
        groups.setdefault(root, []).append(i)

    out = []
    for g in groups.values():
        if len(g) > 1:
            out.append({"wallets": sorted(g), "level": "proven"})

    # 2. Add packs (wallets that entered together) not already in proven groups
    in_proven = {w for o in out for w in o["wallets"]}
    packs: Dict[int, Set[int]] = {}
    for l in links:
        if l.get("level") == "pack":
            a = int(l.get("a", 0))
            b = int(l.get("b", 0))
            if 0 <= a < n and 0 <= b < n:
                packs.setdefault(a, {a}).add(b)

    for s in packs.values():
        unlinked = [w for w in s if w not in in_proven]
        if len(unlinked) >= 2:
            out.append({"wallets": sorted(unlinked), "level": "pack"})
            in_proven.update(unlinked)

    # 3. Add single unclustered wallets
    taken = {w for o in out for w in o["wallets"]}
    for i in range(n):
        if i not in taken:
            out.append({"wallets": [i], "level": None})

    # Compute shares and weighted shares
    for o in out:
        o["share"] = sum(float(holders[i].get("share", 0.0)) for i in o["wallets"])
        o["weighted"] = o["share"] * (0.6 if o["level"] == "pack" else 1.0)

    # Sort largest weighted operator first
    out.sort(key=lambda x: x["weighted"], reverse=True)

    # Assign IDs
    counter = 0
    res = []
    for o in out:
        op_id = None
        if len(o["wallets"]) > 1:
            counter += 1
            op_id = f"OP-{counter}"
            for i in o["wallets"]:
                holders[i]["op"] = op_id

        res.append({
            "id": op_id,
            "wallets": o["wallets"],
            "share": round(o["share"], 4),
            "level": o["level"] if len(o["wallets"]) > 1 else None,
            "weighted": round(o["weighted"], 4),
        })

    return res


def score_token(
    holders: List[Dict[str, Any]],
    operators: List[Dict[str, Any]],
    float_tokens: float,
    reserve_tokens: float,
    liquidity_usd: Optional[float] = None,
    unread_count: int = 0,
) -> Dict[str, Any]:
    """Execute QuantOrb safety score model on holders and operators."""
    real_operators = [o for o in operators if len(o["wallets"]) > 1]
    biggest_op = operators[0] if operators else None

    # Price impact of the largest operator
    op_tokens = (biggest_op.get("weighted", biggest_op.get("share", 0.0)) * float_tokens) if biggest_op else 0.0
    impact = constant_product_impact(op_tokens, reserve_tokens)

    non_dev = [h for h in holders if not h.get("dev")]
    read_wallets = [h for h in non_dev if not h.get("unread")]

    # Calculate metrics
    virgin_ratio = (
        sum(1 for h in read_wallets if h.get("virgin")) / max(1, len(read_wallets))
        if read_wallets
        else 0.0
    )
    transfer_share = sum(float(h.get("share", 0.0)) for h in holders if h.get("kind") == "transfer")
    sniper_share = sum(float(h.get("share", 0.0)) for h in non_dev if h.get("sniper") and not h.get("sold"))
    concentration = sum(float(h.get("share", 0.0)) for h in holders)

    # Parts
    parts = {
        "operator": _linear_part("operator", impact),
        "virgin": _linear_part("virgin", virgin_ratio),
        "transfer": _linear_part("transfer", transfer_share),
        "sniper": _linear_part("sniper", sniper_share),
        "concentration": _linear_part("concentration", concentration),
    }

    raw_total = sum(parts.values())
    total_score = round(raw_total)

    # Hard and Soft Risk Gates
    gates = []

    # Hard Gate 1: Biggest operator impact >= 50% with multiple linked wallets
    if biggest_op and impact >= 0.50 and len(biggest_op["wallets"]) > 1:
        gates.append({
            "hard": True,
            "text": f"Biggest operator could drop price -{round(impact*100)}% if sold ({biggest_op['share']*100:.1f}% float, {len(biggest_op['wallets'])} linked wallets)",
        })

    # Hard Gate 2: >= 80% virgin wallets
    if virgin_ratio >= 0.80 and read_wallets:
        gates.append({
            "hard": True,
            "text": f"{round(virgin_ratio*100)}% of top wallets never traded before this token",
        })

    # Hard Gate 3: >= 10% float transferred without buy
    if transfer_share >= 0.10:
        gates.append({
            "hard": True,
            "text": f"{transfer_share*100:.1f}% of float was received by transfer, not bought",
        })

    # Soft Cap: Proven operators with >= 3 wallets
    for o in real_operators:
        if o.get("level") == "pack" or len(o["wallets"]) >= 3:
            gates.append({
                "hard": False,
                "text": f"Operator of {len(o['wallets'])} wallets holds {o['share']*100:.1f}% of float",
            })

    # Soft Cap: Single whale impact >= 50% (thin liquidity)
    if biggest_op and impact >= 0.50 and len(biggest_op["wallets"]) == 1:
        gates.append({
            "hard": False,
            "text": f"One holder could move price -{round(impact*100)}% (thin liquidity)",
        })

    # Soft Cap: Low liquidity (< $1,000 USD)
    if liquidity_usd is not None and liquidity_usd < 1000.0:
        gates.append({
            "hard": False,
            "text": f"Liquidity is only ${liquidity_usd:.2f} · verdict capped at RISKY",
        })

    has_hard = any(g["hard"] for g in gates)
    has_soft = any(not g["hard"] for g in gates)

    if unread_count >= 3:
        gates.append({
            "hard": False,
            "text": f"{unread_count} of {len(holders)} wallets could not be read in time · verdict capped at RISKY",
        })
        has_soft = True

    if has_soft:
        total_score = min(total_score, 59)

    # Categorical Band
    if has_hard:
        band = "DANGER"
    elif total_score >= 80:
        band = "CLEAN"
    elif total_score >= 60:
        band = "OK"
    elif total_score >= 40:
        band = "RISKY"
    else:
        band = "DANGER"

    # Dump Sell Scenario
    scenario = None
    if band == "DANGER":
        scenario = calculate_sell_scenario(holders, operators, float_tokens, reserve_tokens)

    headline = (
        f"{len(holders)} wallets → {len(operators)} operators, biggest holds "
        f"{biggest_op['share']*100:.1f}% of float" if biggest_op else ""
    )
    if impact >= 0.01:
        headline += f", could drop price -{round(impact*100)}% if sold"

    return {
        "score": total_score,
        "band": band,
        "parts": parts,
        "metrics": {
            "largest_operator_impact": round(impact, 4),
            "virgin_wallet_ratio": round(virgin_ratio, 4),
            "transferred_float_ratio": round(transfer_share, 4),
            "sniper_holdings_ratio": round(sniper_share, 4),
            "top_concentration_ratio": round(concentration, 4),
        },
        "gates": gates,
        "scenario": scenario,
        "headline": headline,
    }


def guard_checks(
    creator_launched: int = 0,
    creator_graduated: int = 0,
    slot0_share: Optional[float] = None,
    dev_share: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute QuantOrb Guard rules on creator history, slot-0 snipers, and dev holdings."""
    checks = []

    # 1. Creator history: >= 10 launches and < 10% graduated is held
    if creator_launched >= 10 and (creator_graduated * 100 < 10 * creator_launched):
        checks.append({
            "name": "Creator history",
            "passed": False,
            "reason": f"Serial creator: {creator_launched} launches, only {creator_graduated} graduated",
        })
    else:
        checks.append({
            "name": "Creator history",
            "passed": True,
            "text": f"{creator_launched} tokens launched, {creator_graduated} graduated",
        })

    # 2. Slot-0 snipers: >= 30% of supply bought in launch slot is held
    if slot0_share is not None and slot0_share >= 0.30:
        checks.append({
            "name": "First-slot buyers",
            "passed": False,
            "reason": f"{slot0_share*100:.1f}% bought in the first slot",
        })
    elif slot0_share is not None:
        checks.append({
            "name": "First-slot buyers",
            "passed": True,
            "text": f"{slot0_share*100:.1f}% bought in launch slot",
        })

    # 3. Dev holdings: >= 15% of supply held after launch
    if dev_share is not None and dev_share >= 0.15:
        checks.append({
            "name": "Dev holdings",
            "passed": False,
            "reason": f"Dev still holds {dev_share*100:.1f}% after launch",
        })
    elif dev_share is not None:
        checks.append({
            "name": "Dev holdings",
            "passed": True,
            "text": f"Dev holds {dev_share*100:.1f}% of supply",
        })

    all_passed = all(c.get("passed", True) for c in checks)
    failed = [c for c in checks if not c.get("passed")]

    return {
        "pass": all_passed,
        "reason": failed[0]["reason"] if failed else None,
        "checks": checks,
    }
