"""Offline behavioral tests; no network, Ollama, or existing runtime databases."""
import copy
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from cryptoscope.agents.graph import ResearchGraph
from cryptoscope.agents.risk.policy import validate
from cryptoscope.agents.schemas import Proposal, Snapshot
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.providers.binance import BinanceProvider
from cryptoscope.providers.laya import LayaProvider
from cryptoscope.providers.contracts import role_schema
from cryptoscope.research.demo import DemoProvider, demo_snapshot
from cryptoscope.research.settings import load_config
from cryptoscope.storage.research_store import ResearchStore


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config()
        self.snapshot = demo_snapshot()
        self.provider = DemoProvider(self.snapshot)
        self.proposal = Proposal.parse(self.provider.complete("trader", {}), "BTCUSDT")
        self.broker = PaperBroker(self.root / "paper.db", self.config)

    def quote(self):
        return self.provider.quote("BTCUSDT")

    def graph(self, provider=None):
        return ResearchGraph(provider or self.provider, ResearchStore(self.root), self.broker,
                             self.config, self.root / "reports")

    def test_point_in_time_and_candle_integrity(self):
        changes = [lambda d: d["candles"][-1].update(close_time=d["as_of"] + 1),
                   lambda d: d["candles"][-1].update(close=float("nan")),
                   lambda d: d["candles"][-1].update(taker_buy_volume=1000),
                   lambda d: d["candles"][-1].update(open_time=d["candles"][-2]["open_time"]),
                   lambda d: d.update(news=[{"headline": "future", "source": "test", "published_at": d["as_of"] + 1, "available_at": d["as_of"] + 1}])]
        for change in changes:
            with self.subTest(change=change):
                data = copy.deepcopy(self.snapshot.to_dict())
                change(data)
                with self.assertRaises(ValueError):
                    Snapshot.parse(data)

    def test_bad_proposal_refused(self):
        for changes in ({"confidence": True}, {"symbol": "ETHUSDT"}, {"action": "BUY"},
                        {"stop": None}, {"entry": float("inf")}, {"reduce_fraction": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Proposal.parse({**self.proposal.to_dict(), **changes}, "BTCUSDT")

    def test_fee_aware_sizing_and_idempotence(self):
        quote = self.quote()
        fill = self.broker.execute("same-run", self.proposal, self.snapshot, quote)
        self.assertEqual(fill["status"], "filled")
        self.assertLessEqual(fill["price"] * fill["quantity"], 1000.000001)
        self.assertGreaterEqual(self.broker.portfolio()["cash"], 0)
        cash = self.broker.portfolio()["cash"]
        self.assertEqual(self.broker.execute("same-run", self.proposal, self.snapshot, quote), fill)
        self.assertEqual(self.broker.portfolio()["cash"], cash)
        duplicate = self.broker.execute("other-run", self.proposal, self.snapshot, quote)
        self.assertEqual(duplicate["status"], "rejected")

    def test_stop_risk_budget_includes_costs(self):
        fill = self.broker.execute("buy", self.proposal, self.snapshot, self.quote())
        exit_price = self.proposal.stop * (1 - self.config["slippage_fraction"])
        loss = fill["quantity"] * (fill["price"] - exit_price) + fill["fee"] + exit_price * fill["quantity"] * self.config["fee_fraction"]
        self.assertLessEqual(loss, 50.000001)

    def test_concurrent_delivery_creates_one_fill(self):
        quote = self.quote()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fills = list(pool.map(lambda _: self.broker.execute(
                "concurrent-run", self.proposal, self.snapshot, quote), range(2)))
        self.assertEqual(fills[0], fills[1])
        self.assertAlmostEqual(self.broker.portfolio()["cash"],
                               10000 - fills[0]["quantity"] * fills[0]["price"] - fills[0]["fee"])

    def test_stale_quote_and_snapshot_refused(self):
        quote = {**self.quote(), "available_at": time.time() - 100}
        self.assertIn("STALE_OR_FUTURE_QUOTE", validate(self.proposal, self.snapshot, self.broker.portfolio(), quote, self.config)["reasons"])
        gate = validate(self.proposal, self.snapshot, self.broker.portfolio(), self.quote(), self.config,
                        now=self.snapshot.as_of + 90000)
        self.assertIn("STALE_OR_FUTURE_SNAPSHOT", gate["reasons"])

    def test_net_reward_risk_drift_and_short_guards(self):
        for changes, reason in (({"target": self.proposal.entry * 1.01}, "INSUFFICIENT_NET_REWARD_RISK"),
                                ({"entry": self.proposal.entry * 0.9}, "ENTRY_DRIFT_EXCEEDED"),
                                ({"action": "SHORT"}, "SPOT_SHORT_NOT_SUPPORTED")):
            proposal = Proposal.parse({**self.proposal.to_dict(), **changes}, "BTCUSDT")
            gate = validate(proposal, self.snapshot, self.broker.portfolio(), self.quote(), self.config)
            self.assertFalse(gate["approved"])
            self.assertIn(reason, gate["reasons"])

    def test_partial_close_and_gap_stop_accounting(self):
        self.broker.execute("buy", self.proposal, self.snapshot, self.quote())
        initial = self.broker.portfolio()["positions"]["BTCUSDT"]["quantity"]
        reduction = Proposal.parse({**self.proposal.to_dict(), "action": "REDUCE", "reduce_fraction": 0.5}, "BTCUSDT")
        self.broker.execute("reduce", reduction, self.snapshot, self.quote())
        self.assertAlmostEqual(self.broker.portfolio()["positions"]["BTCUSDT"]["quantity"], initial / 2)
        gap_bid = self.proposal.stop * 0.9
        fill = self.broker.mark({**self.quote(), "bid": gap_bid})
        self.assertEqual(fill["reason"], "stop")
        self.assertLess(fill["price"], gap_bid)
        self.assertEqual(self.broker.portfolio()["positions"], {})
        self.assertEqual(self.broker.mark(self.quote())["status"], "no_position")

    def test_full_workflow_persists_report_and_fill(self):
        result = self.graph().run(self.snapshot, self.provider.quote, paper=True)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(result["execution"]["status"], "filled")
        report = Path(result["report_directory"]) / "report.json"
        body = json.loads(report.read_text())
        self.assertEqual(body["model"], "DEMO_FIXTURE_NOT_LAYA")
        self.assertEqual(len(body["model_calls"]), 7)

    def test_model_outage_records_failure_without_order(self):
        class Offline(DemoProvider):
            def complete(self, role, context):
                raise ConnectionError("Ollama unavailable")
        result = self.graph(Offline(self.snapshot)).run(self.snapshot, self.provider.quote, True)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Ollama unavailable", result["error"])
        self.assertEqual(self.broker.portfolio()["cash"], 10000)
        self.assertTrue((Path(result["report_directory"]) / "report.json").exists())

    def test_invalid_portfolio_approval_and_missing_evidence_fail_closed(self):
        class BadApproval(DemoProvider):
            def complete(self, role, context):
                result = super().complete(role, context)
                if role == "portfolio_manager":
                    result["approved"] = "true"
                return result
        class MissingEvidence(DemoProvider):
            def complete(self, role, context):
                result = super().complete(role, context)
                if role == "trader":
                    result["evidence"] = ["news"]
                return result
        for provider in (BadApproval(self.snapshot), MissingEvidence(self.snapshot)):
            result = self.graph(provider).run(self.snapshot, self.provider.quote, True)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(self.broker.portfolio()["cash"], 10000)

    def test_binance_discards_open_candles(self):
        data = self.snapshot.to_dict()
        rows = [[int(c["open_time"] * 1000), str(c["open"]), str(c["high"]), str(c["low"]),
                 str(c["close"]), str(c["volume"]), int(c["close_time"] * 1000) - 1,
                 "0", 1, str(c["taker_buy_volume"])] for c in data["candles"]]
        last = rows[-1].copy()
        last[0] += 900000
        last[6] += 900000
        rows.append(last)
        def get(path, **kwargs):
            return {"serverTime": int(data["as_of"] * 1000)} if path.endswith("time") else rows
        feed = BinanceProvider()
        with patch.object(feed, "get", side_effect=get):
            snapshot = feed.snapshot("BTCUSDT", "15m")
        self.assertEqual(len(snapshot.candles), 60)

    def test_laya_requests_json_and_exact_model(self):
        import io
        response = io.BytesIO(json.dumps({"done": True, "response": '{"approved": false}'}).encode())
        with patch("cryptoscope.providers.laya.urlopen", return_value=response) as call:
            provider = LayaProvider(self.config)
            self.assertEqual(provider.complete("test", {}), {"approved": False})
            payload = json.loads(call.call_args.args[0].data)
            self.assertEqual(payload["model"], provider.model)
            self.assertEqual(payload["format"], "json")
            self.assertFalse(payload["stream"])
            self.assertFalse(payload["think"])

    def test_role_schema_enforces_handoff_fields(self):
        context = {"analysts": [{"id": "technical", "status": "available"},
                                 {"id": "news", "status": "unavailable"}],
                   "instrument": {"symbol": "BTCUSDT", "as_of": self.snapshot.as_of}}
        schema = role_schema("bull_researcher", context)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"thesis", "evidence", "counterarguments"})
        self.assertEqual(schema["properties"]["evidence"]["items"]["enum"], ["technical"])
        self.assertEqual(role_schema("trader", context)["properties"]["symbol"]["enum"], ["BTCUSDT"])

    def test_native_schema_is_sent_to_ollama(self):
        import io
        response = io.BytesIO(json.dumps({"done": True, "done_reason": "stop", "eval_count": 30,
            "response": '{"thesis":"Trend", "evidence":["technical"], "counterarguments":[]}'}).encode())
        with patch("cryptoscope.providers.laya.urlopen", return_value=response) as call:
            provider = LayaProvider(self.config)
            provider.complete("bull_researcher", {"output_contract": {"old": "pseudo-schema"}})
            payload = json.loads(call.call_args.args[0].data)
            self.assertEqual(payload["format"]["type"], "object")
            self.assertFalse(payload["format"]["additionalProperties"])
            self.assertNotIn("output_contract", payload["prompt"])

    def test_truncated_output_is_logged_and_never_parsed_as_success(self):
        import io
        raw=json.dumps({"done": True, "done_reason": "length", "eval_count": 512,
                        "response": '{"thought":"unfinished'}).encode()
        provider = LayaProvider(self.config)
        with patch("cryptoscope.providers.laya.urlopen", side_effect=[io.BytesIO(raw),io.BytesIO(raw)]):
            with self.assertRaisesRegex(RuntimeError, "reason=length"):
                provider.complete("bull_researcher", {})
        self.assertEqual(provider.calls[0]["status"], "failed")
        self.assertEqual(provider.calls[0]["output_tokens"], 512)
        self.assertIn("unfinished", provider.calls[0]["raw_response"])
        self.assertEqual(len(provider.calls),2)
        self.assertEqual(provider.calls[1]['status'],'failed')

    def test_malformed_json_gets_one_audited_regeneration_with_the_same_model(self):
        import io
        invalid={'done':True,'done_reason':'stop','response':'{"assessment":"unfinished'}
        valid={'done':True,'done_reason':'stop','response':'{"assessment":"Uncertain","concerns":["Missing news"]}'}
        provider=LayaProvider(self.config)
        with patch('cryptoscope.providers.laya.urlopen',side_effect=[io.BytesIO(json.dumps(v).encode()) for v in (invalid,valid)]) as calls:
            result=provider.complete('neutral_risk',{'proposal':{'action':'HOLD'}})
            self.assertEqual(result['assessment'],'Uncertain')
            self.assertEqual([call['status'] for call in provider.calls],['failed','completed'])
            payloads=[json.loads(call.args[0].data) for call in calls.call_args_list]
            self.assertEqual([p['model'] for p in payloads],[provider.model,provider.model])
            self.assertEqual(payloads[1]['format']['properties']['concerns']['maxItems'],1)
            self.assertTrue(provider.calls[1]['concise_retry'])

    def test_network_failure_is_not_retried(self):
        provider=LayaProvider(self.config)
        with patch('cryptoscope.providers.laya.urlopen',side_effect=TimeoutError('offline')) as calls:
            with self.assertRaises(RuntimeError):
                provider.complete('neutral_risk',{})
            self.assertEqual(calls.call_count,1)

    def test_invalid_numeric_output_is_regenerated_not_coerced(self):
        import io
        proposal=self.proposal.to_dict()
        proposal.update(reduce_fraction=0)
        fixed={**proposal,'reduce_fraction':1,'thesis':'Concise valid response.'}
        provider=LayaProvider(self.config)
        context={'instrument':{'symbol':'BTCUSDT','as_of':self.snapshot.as_of},
                 'analysts':[{'id':'technical','status':'available'}]}
        responses=[{'done':True,'done_reason':'stop','response':json.dumps(value)} for value in (proposal,fixed)]
        with patch('cryptoscope.providers.laya.urlopen',side_effect=[io.BytesIO(json.dumps(v).encode()) for v in responses]):
            output=provider.complete('trader',context)
        self.assertEqual(output['reduce_fraction'],1)
        self.assertEqual(provider.calls[0]['status'],'failed')
        self.assertIn('reduce_fraction',provider.calls[0]['error'])
        self.assertEqual(json.loads(provider.calls[0]['raw_response'])['reduce_fraction'],0)
        self.assertEqual(provider.calls[1]['status'],'completed')

    def test_local_schema_refuses_bools_unknown_evidence_and_missing_fields(self):
        from cryptoscope.providers.contracts import validate_schema,SchemaValidationError
        context={'instrument':{'symbol':'BTCUSDT','as_of':self.snapshot.as_of},
                 'analysts':[{'id':'technical','status':'available'}]}
        schema=role_schema('trader',context)
        base=self.proposal.to_dict()
        base['reduce_fraction']=1
        validate_schema(base,schema)
        for change in ({'reduce_fraction':False},{'confidence':float('nan')},{'evidence':['nonexistent']},
                       {'extra':'no'},{'symbol':'ETHUSDT'}):
            with self.subTest(change=change),self.assertRaises(SchemaValidationError):
                validate_schema({**base,**change},schema)
        with self.assertRaises(SchemaValidationError):
            validate_schema({k:v for k,v in base.items() if k!='symbol'},schema)


if __name__ == "__main__":
    unittest.main()
