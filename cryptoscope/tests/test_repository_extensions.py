import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from cryptoscope.agents.graph import ResearchGraph
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.backtesting.validation import bootstrap, performance
from cryptoscope.execution.paper_broker import PaperBroker
from cryptoscope.forecasting import snapshot_hash, validate_forecast
from cryptoscope.providers.contracts import role_schema
from cryptoscope.research.demo import demo_snapshot, DemoProvider
from cryptoscope.research.settings import ROOT, load_config
from cryptoscope.storage.research_store import ResearchStore
from cryptoscope.strategy import StrategySpec, draft


def forecast_fixture(snapshot):
    price=snapshot.candles[-1]['close']
    return {'status':'completed','symbol':snapshot.symbol,'model':'TEST_FIXTURE_NOT_KRONOS',
        'input_hash':snapshot_hash(snapshot),'input_cutoff':snapshot.as_of,
        'available_at':time.time(), 'parameters':{'steps':2},
        'forecast':[{'open_time':snapshot.candles[-1]['close_time']+i*snapshot.interval_seconds,
                     'open':price,'high':price+1,'low':price-1,'close':price+.2} for i in range(2)]}


class RepositoryExtensionTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config()
        self.snapshot=demo_snapshot()

    def test_forecast_binding_latency_and_numeric_boundaries(self):
        original=forecast_fixture(self.snapshot)
        self.assertIs(validate_forecast(original,self.snapshot),original)
        for change in (lambda r:r.update(input_hash='another-input'),
                       lambda r:r.update(input_cutoff=snapshot_hash(self.snapshot)),
                       lambda r:r.update(available_at=time.time()+100),
                       lambda r:r['forecast'][0].update(open_time=self.snapshot.candles[-1]['open_time']),
                       lambda r:r['forecast'][0].update(close=float('nan')),
                       lambda r:r['forecast'][0].update(low=r['forecast'][0]['high']+1)):
            report=copy.deepcopy(original)
            change(report)
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_forecast(report,self.snapshot)

    def test_forecast_reaches_laya_context_but_cannot_execute_orders(self):
        class Capture(DemoProvider):
            def complete(self,role,context):
                if role=='trader':
                    self.trader_context=context
                return super().complete(role,context)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            provider=Capture(self.snapshot)
            broker=PaperBroker(root/'paper.db',self.config)
            graph=ResearchGraph(provider,ResearchStore(root),broker,self.config,root/'reports',
                                forecast_supplier=forecast_fixture)
            body=graph.run(self.snapshot,provider.quote,paper=False)
            self.assertEqual(body['status'],'completed')
            self.assertIn('kronos',[a['id'] for a in provider.trader_context['analysts']])
            self.assertEqual(broker.portfolio()['positions'],{})
            self.assertEqual(body['execution']['status'],'research_only')

    def test_strategy_specs_reject_code_risk_overrides_and_unknown_templates(self):
        valid={'name':'EMA study','symbol':'BTCUSDT','strategy':'ema_baseline',
               'fast':10,'slow':30,'rationale':'Research template only.'}
        self.assertEqual(StrategySpec.parse(valid,self.config).fast,10)
        for change in ({'code':'import os'},{'max_position_fraction':1},
                       {'strategy':'arbitrary_python'},{'fast':True},{'slow':5},{'symbol':'DOGEUSDT'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                StrategySpec.parse({**valid,**change},self.config)
        class Provider:
            def complete(self,role,context):
                return {**valid,'symbol':'ETHUSDT'}
        with self.assertRaises(ValueError):
            draft('EMA study','BTCUSDT',self.config,Provider())
        self.assertEqual(role_schema('strategy_designer',{'symbol':'BTCUSDT'})['properties']['strategy']['enum'],
                         ['ema_baseline','buy_hold_baseline','unsupported'])

    def test_crypto_calendar_and_degenerate_metrics(self):
        result=performance([100,100,100],100,900)
        self.assertEqual(result['annual_bars'],365*96)
        self.assertIsNone(result['sharpe_zero_rf'])
        self.assertIsNone(result['sortino_zero_rf'])
        self.assertEqual(result['annualized_volatility_pct'],0)
        for nav in (float('nan'),0,-1):
            with self.assertRaises(ValueError):
                performance([100,nav],100,900)

    def test_block_bootstrap_is_reproducible_and_does_not_invent_confidence(self):
        a=bootstrap([100,99,101,100],100,paths=40,block_length=2,seed=7)
        self.assertEqual(a,bootstrap([100,99,101,100],100,paths=40,block_length=2,seed=7))
        self.assertLessEqual(a['return_pct_p05'],a['return_pct_median'])
        self.assertLessEqual(a['return_pct_median'],a['return_pct_p95'])
        self.assertEqual(bootstrap([100,100,100],100)['empirical_loss_fraction'],0)

    def test_kronos_source_matches_pinned_git_blobs_with_only_line_ending_normalization(self):
        manifest=json.loads((ROOT/'integrations/kronos/provenance.json').read_text())
        for entry in manifest['files']:
            content=(ROOT/'integrations/kronos/vendor'/entry['path']).read_bytes()
            lf=content.replace(b'\r\n',b'\n')
            variants=[content,lf,lf.replace(b'\n',b'\r\n')]
            hashes=[hashlib.sha1(b'blob '+str(len(v)).encode()+b'\0'+v).hexdigest() for v in variants]
            self.assertIn(entry['git_blob_sha'],hashes,entry['path'])


try:
    import backtester
except ImportError:
    backtester=None


@unittest.skipIf(backtester is None,'Use the optional backtesting environment')
class ChronologicalValidationTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config()
        base=demo_snapshot().to_dict()
        end=base['candles'][-1]['close_time']
        base['candles']=[]
        for i in range(200):
            price=100+math.sin(i/10)*4+i*.02
            base['candles'].append({'open_time':end-(200-i)*900,'close_time':end-(199-i)*900,
                'open':price,'close':price+.1,'high':price+.3,'low':price-.3,'volume':100,'taker_buy_volume':50})
        self.snapshot=Snapshot.parse(base)

    def test_no_test_data_in_selection_and_no_positions_before_test_boundary(self):
        from cryptoscope.backtesting.validation import walk_forward
        first=walk_forward(self.snapshot,self.config)
        data=self.snapshot.to_dict()
        for bar in data['candles'][-20:]:
            for key in ('open','high','low','close'):
                bar[key]*=2
        changed=walk_forward(Snapshot.parse(data),self.config)
        self.assertEqual(first['folds'][0],changed['folds'][0])
        self.assertEqual(first['metrics']['fills'],len(first['fills']))
        self.assertAlmostEqual(first['metrics']['fees'],sum(f['fee'] for f in first['fills']))
        for fold in first['folds']:
            self.assertGreaterEqual(fold['test_start']-fold['train_end'],1800)
        for fill in first['fills']:
            fold=first['folds'][fill['fold']-1]
            self.assertGreater(fill['executed_at'],fold['test_start'])
            self.assertLess(fill['executed_at'],fold['test_end'])
        self.assertEqual(first['equity'][-1]['position'],0)

    def test_cost_stress_reduces_returns_and_benchmark_uses_same_policy(self):
        from cryptoscope.backtesting.validation import robustness
        report=robustness(self.snapshot,self.config)
        returns=[row['metrics']['net_return_pct'] for row in report['cost_sensitivity']]
        self.assertGreater(returns[0],returns[-1])
        self.assertIn('Same capital',report['comparison']['policy'])
        self.assertEqual(report['bootstrap']['seed'],42)

    def test_incomplete_fold_is_not_reported_as_validation(self):
        from cryptoscope.backtesting.validation import walk_forward
        with self.assertRaises(ValueError):
            walk_forward(demo_snapshot(),self.config)
