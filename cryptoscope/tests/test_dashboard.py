"""Dashboard reads real ledger contracts and treats report text as untrusted."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.dashboard.__main__ import handler_for
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.tests.demo_fixtures import demo_snapshot
from cryptoscope.research.settings import load_config


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config()
        self.data = DashboardData(self.root, self.config)
        self.data.model_health = lambda: {"model": "laya-crypto:latest", "status": "ready"}


    def test_empty_monitor_creates_no_runtime_files(self):
        state = self.data.overview("research")
        self.assertEqual(state["runs"], [])
        self.assertIsNone(state["portfolio"]["cash"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_busy_ollama_timeout_is_distinguished_from_connection_failure(self):
        data=DashboardData(self.root,self.config)
        with patch('cryptoscope.dashboard.data.LayaProvider.models',side_effect=TimeoutError('busy')):
            self.assertEqual(data.model_health()['status'],'check_delayed')
        data.checked_at=0
        with patch('cryptoscope.dashboard.data.LayaProvider.models',side_effect=ConnectionRefusedError('offline')):
            self.assertEqual(data.model_health()['status'],'unreachable')


    def test_validation_and_missing_runs(self):
        for workspace in ("../runtime", "LIVE", ""):
            with self.assertRaises(ValueError):
                self.data.overview(workspace)
        with self.assertRaises(ValueError):
            self.data.run("research", "../../secrets")
        self.assertIsNone(self.data.run("research", "a" * 32))

    def handler(self, path, host="localhost:8900"):
        handler = handler_for(self.data).__new__(handler_for(self.data))
        handler.path, handler.headers = path, {"Host": host}
        handler.server = SimpleNamespace(server_address=("127.0.0.1", 8900))
        handler.json, handler.send = Mock(), Mock()
        return handler

    def test_http_routes_reject_remote_hosts_and_path_traversal(self):
        handler = self.handler("/api/dashboard", "example.com:8900")
        handler.do_GET()
        self.assertEqual(handler.json.call_args.args[0], 403)
        handler = self.handler("/../../config/research.json")
        handler.do_GET()
        self.assertEqual(handler.json.call_args.args[0], 404)
        handler = self.handler("/api/dashboard?workspace=bad")
        handler.do_GET()
        self.assertEqual(handler.json.call_args.args[0], 400)


    def test_forecast_and_strategy_artifacts_are_read_only(self):
        run_id='f'*32
        for kind,body in [('forecasts',{'status':'completed','symbol':'BTCUSDT','source':'binance_spot',
            'available_at':100,'parameters':{'steps':2},'forecast':[]}),
            ('strategies',{'status':'draft_not_backtested','spec':{'name':'Study'}})]:
            path=self.root/'reports'/kind/run_id/'report.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(body))
            original=path.read_bytes()
            handler=self.handler(f'/api/{kind}/{run_id}?download=1')
            handler.do_GET()
            self.assertEqual(handler.json.call_args.args[0],200)
            self.assertEqual(handler.json.call_args.args[2],f'zien-{kind}-{run_id}.json')
            self.assertEqual(path.read_bytes(),original)
            bad=self.handler(f'/api/{kind}/../../secrets')
            bad.do_GET()
            self.assertEqual(bad.json.call_args.args[0],400)
        real=self.data.overview('research')
        self.assertEqual(real['forecast']['run_id'],run_id)
        self.assertIsNotNone(real['strategy'])

    def test_strategy_links_to_matching_backtest_without_changing_the_original_draft(self):
        draft_id='a'*32
        test_id='b'*32
        spec={'name':'EMA study','strategy':'ema_baseline','fast':10,'slow':30,'symbol':'BTCUSDT'}
        draft=self.root/'reports/strategies'/draft_id/'report.json'
        test=self.root/'reports/backtests'/test_id/'report.json'
        draft.parent.mkdir(parents=True)
        test.parent.mkdir(parents=True)
        draft.write_text(json.dumps({'spec':spec,'status':'draft_not_backtested'}))
        original=draft.read_bytes()
        test.write_text(json.dumps({'run_id':test_id,'source':'binance_spot','strategy_spec':spec,'metrics':{'net_return_pct':-.1}}))
        self.assertEqual(self.data.latest_strategy('research')['backtest']['run_id'],test_id)
        self.assertEqual(draft.read_bytes(),original)

