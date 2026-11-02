"""Tests for on-chain token safety scoring, AMM impact, and QuantOrb rules."""
import pytest
from cryptoscope.risk_tools.amm_impact import constant_product_impact, calculate_sell_scenario
from cryptoscope.risk_tools.onchain_guard import (
    cluster_operators,
    score_token,
    guard_checks,
)


class TestOnchainGuard:
    def test_constant_product_impact(self):
        # 1 - (R / (R + q))^2
        # If R=100 and q=100: 1 - (100 / 200)^2 = 1 - 0.25 = 0.75 (75% drop)
        assert constant_product_impact(100.0, 100.0) == pytest.approx(0.75, rel=1e-3)
        assert constant_product_impact(0.0, 100.0) == 0.0
        assert constant_product_impact(100.0, 0.0) == 0.0

    def test_cluster_operators_disjoint_set(self):
        holders = [{"share": 0.05} for _ in range(5)]
        links = [
            {"a": 0, "b": 1, "level": "proven"},
            {"a": 1, "b": 2, "level": "proven"},  # 0, 1, 2 should merge into one operator
        ]
        ops = cluster_operators(holders, links)
        # Should have one OP with 3 wallets and 2 single-wallet operators
        real_ops = [o for o in ops if o["id"]]
        assert len(real_ops) == 1
        assert real_ops[0]["wallets"] == [0, 1, 2]
        assert real_ops[0]["share"] == pytest.approx(0.15, rel=1e-3)

    def test_score_token_clean_twenty_wallets(self):
        # 20 independent experienced wallets, no links, no virgin wallets
        holders = [{"share": 0.02, "virgin": False, "kind": "buy"} for _ in range(20)]
        ops = cluster_operators(holders, [])
        res = score_token(holders, ops, float_tokens=1_000_000, reserve_tokens=1_000_000, liquidity_usd=50_000)

        assert res["score"] >= 80
        assert res["band"] == "CLEAN"
        assert res["scenario"] is None

    def test_red_flag_virgin_wallets_forces_danger(self):
        # 20 wallets, 90% virgin
        holders = [{"share": 0.02, "virgin": True, "kind": "buy"} for _ in range(18)]
        holders += [{"share": 0.02, "virgin": False, "kind": "buy"} for _ in range(2)]
        ops = cluster_operators(holders, [])
        res = score_token(holders, ops, float_tokens=1_000_000, reserve_tokens=1_000_000, liquidity_usd=50_000)

        assert res["band"] == "DANGER"
        assert any(g["hard"] for g in res["gates"])

    def test_red_flag_transferred_supply_forces_danger(self):
        # 15% of float received by transfer
        holders = [{"share": 0.15, "virgin": False, "kind": "transfer"}]
        holders += [{"share": 0.02, "virgin": False, "kind": "buy"} for _ in range(10)]
        ops = cluster_operators(holders, [])
        res = score_token(holders, ops, float_tokens=1_000_000, reserve_tokens=1_000_000, liquidity_usd=50_000)

        assert res["band"] == "DANGER"
        assert any("received by transfer" in g["text"] for g in res["gates"])

    def test_largest_operator_dump_scenario(self):
        # One large operator holding 60% of float
        holders = [
            {"share": 0.30, "virgin": False, "kind": "buy"},
            {"share": 0.30, "virgin": False, "kind": "buy"},
        ]
        links = [{"a": 0, "b": 1, "level": "proven"}]
        ops = cluster_operators(holders, links)
        # Pool: float=100k, reserve=50k -> q=60k -> 1 - (50 / 110)^2 = 1 - 0.2066 = ~79% drop
        res = score_token(holders, ops, float_tokens=100_000, reserve_tokens=50_000, liquidity_usd=20_000)

        assert res["band"] == "DANGER"
        assert res["scenario"] is not None
        assert res["scenario"]["price_drop_pct"] >= 50.0

    def test_guard_checks_creator_and_dev(self):
        # Serial creator: 15 launches, only 1 graduated (< 10%)
        g1 = guard_checks(creator_launched=15, creator_graduated=1)
        assert not g1["pass"]
        assert "Serial creator" in g1["reason"]

        # Honest creator: 3 launches, 2 graduated
        g2 = guard_checks(creator_launched=3, creator_graduated=2, slot0_share=0.05, dev_share=0.08)
        assert g2["pass"]
        assert g2["reason"] is None
