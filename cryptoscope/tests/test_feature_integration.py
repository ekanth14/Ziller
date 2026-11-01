import copy
import json
from pathlib import Path
import tempfile
import unittest
from cryptoscope.dashboard.data import DashboardData
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.agents.schemas import Proposal
from cryptoscope.research.demo import demo_snapshot, DemoProvider
from cryptoscope.research.settings import load_config


class FeatureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config()

    def test_halt_survives_restart_and_blocks_only_entries(self):
        path = self.root/'paper.db'
        broker = PaperBroker(path, self.config)
        snapshot = demo_snapshot()
        provider = DemoProvider(snapshot)
        proposal = Proposal.parse(provider.complete('trader', {}), snapshot.symbol)
        quote = provider.quote(snapshot.symbol)
        broker.set_halt(True)
        restarted = PaperBroker(path, self.config)
        self.assertTrue(restarted.controls()['halted'])
        denied = restarted.execute('blocked', proposal, snapshot, quote)
        self.assertIn('MANUAL_ENTRY_HALT', denied['reasons'])
        restarted.set_halt(False)
        self.assertEqual(restarted.execute('entry', proposal, snapshot, quote)['status'], 'filled')
        restarted.set_halt(True)
        close = Proposal.parse({**proposal.to_dict(), 'action': 'CLOSE'}, snapshot.symbol)
        self.assertEqual(restarted.execute('exit', close, snapshot, quote)['status'], 'filled')

    def test_backtests_and_risk_are_filtered_by_workspace(self):
        for index, source in enumerate(('binance_spot', 'synthetic_demo')):
            run_id = str(index)*32
            path = self.root/'reports/backtests'/run_id
            path.mkdir(parents=True)
            (path/'report.json').write_text(json.dumps({'run_id':run_id, 'source':source,
                'created_at':index, 'risk':{'status':'completed'}, 'metrics':{}}))
        data = DashboardData(self.root, self.config)
        self.assertEqual(len(data.backtests('research')), 1)
        self.assertEqual(data.backtests('demo')[0]['source'], 'synthetic_demo')
        self.assertEqual(data.risk_reports('research')['status'], 'available')
        with self.assertRaises(ValueError):
            data.backtest('../../config/research')

try:
    import backtester
    from cryptoscope.backtesting.runner import evaluate, save_report
except ImportError:
    backtester = None


# SKIPPED TESTS AUDIT: The following 4 integration tests require 'quantjourney-bt' (git-pinned in requirements-backtest.txt),
# an optional specialized backtesting simulator separate from the standard lightweight ZILLERS runtime.
@unittest.skipIf(
    backtester is None,
    "Requires optional 'quantjourney-bt' backtesting engine (git-pinned in requirements-backtest.txt); standard runtime uses stdlib-only backtesting"
)
class BacktestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = demo_snapshot()
        self.config = load_config()

    def test_real_engine_round_trip_and_costs(self):
        report = evaluate(self.snapshot, self.config)
        self.assertEqual(report['decision_source'], 'deterministic_baseline_not_laya')
        self.assertEqual(report['metrics']['fills'], 2)
        self.assertGreater(report['metrics']['fees'], 0)
        self.assertAlmostEqual(report['equity'][-1]['position'], 0)
        self.assertAlmostEqual(report['equity'][-1]['cash'], report['metrics']['final_nav'])
        for fill in report['fills']:
            decision = next(d for d in report['decisions'] if d['order_id']==fill['order_id'])
            self.assertGreaterEqual(fill['executed_at'], decision['available_at'])

    def test_fingerprint_and_artifacts(self):
        a = evaluate(self.snapshot, self.config)
        b = evaluate(self.snapshot, self.config)
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        self.assertEqual(a['metrics'], b['metrics'])
        with tempfile.TemporaryDirectory() as directory:
            saved = save_report(a, directory)
            root = Path(directory)/saved['run_id']
            self.assertTrue((root/'report.json').exists())
            self.assertTrue((root/'equity.csv').exists())
            self.assertTrue((root/'summary.md').exists())

    def test_future_candle_change_does_not_change_earlier_signals(self):
        from cryptoscope.agents.schemas import Snapshot
        before = evaluate(self.snapshot, self.config)
        data = copy.deepcopy(self.snapshot.to_dict())
        for candle in data['candles'][-3:]:
            for key in ('open','close','high','low'):
                candle[key] *= 2
        changed = evaluate(Snapshot.parse(data), self.config)
        cutoff = data['candles'][-3]['open_time']
        clean = lambda report: [{k:v for k,v in d.items() if k!='order_id'} for d in report['decisions'] if d['available_at']<=cutoff]
        self.assertEqual(clean(before),clean(changed))

    def test_invalid_strategy_parameters_refused(self):
        with self.assertRaises(ValueError):
            evaluate(self.snapshot,self.config,fast=50,slow=20)
