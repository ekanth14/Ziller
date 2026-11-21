"""Offline regressions. Synthetic candles/scenarios are not model/exchange evidence."""
import asyncio
import copy
import math

import pytest

from cryptoscope.backtesting.debate_cache import RecordedDebateEngine,debate_key
from cryptoscope.backtesting.fleet_replay import ReplayPipeline,load_archive,replay
from cryptoscope.backtesting.integrity import pair_size,pair_stop_prices,settle_legs,trade_metrics
from cryptoscope.backtesting.risk_exercises import exercise_risk_halts
from cryptoscope.orchestrator.events import TradeIntent


def test_combined_pf_pools_gross_trade_outcomes_not_losing_strategy_totals():
    # Every strategy net is negative, yet 28% of individual trades win.
    trades = [dict(pnl=10)]*28+[dict(pnl=-5)]*72
    result = trade_metrics(trades,10000)
    assert result['win_rate_pct'] == 28
    assert result['profit_factor'] == pytest.approx(280/360)
    assert result['net_pnl_usd'] == -80


@pytest.mark.parametrize('pnls,status,pf',[
    ([], 'no trades or gains',None),([1,2],'no losses',None),
    ([-2,0],'finite',0),([2,-1],'finite',2),
])
def test_profit_factor_undefined_cases_and_sample_label(pnls,status,pf):
    metrics = trade_metrics([dict(pnl=x) for x in pnls],10000)
    assert metrics['profit_factor_status'] == status
    assert metrics['profit_factor'] == pf
    assert metrics['data_quality'] == 'insufficient data'


@pytest.mark.parametrize('beta',[0.25,0.75,1,2,4])
@pytest.mark.parametrize('slippage',[0,0.0005,0.005])
def test_two_leg_adverse_stop_loss_with_fees_within_budget_plus_slippage(beta,slippage):
    plan = pair_size(10000,3000,90000,beta)
    qa,qb = plan['quantity_eth'],plan['quantity_btc']
    assert abs(qb)*90000 == pytest.approx(beta*qa*3000)
    assert plan['planned_loss'] <= plan['risk_budget'] + 1e-8
    legs = [dict(quantity=qa,entry=3000),dict(quantity=qb,entry=90000)]
    result = settle_legs(legs,[plan['stop_eth'],plan['stop_btc']],0.00075,slippage)
    assert -result['pnl'] <= plan['risk_budget']+result['slippage_usd']+1e-8


def test_gap_loss_is_reported_instead_of_fictitiously_capped_at_stop():
    plan = pair_size(10000,3000,90000,1)
    prices = pair_stop_prices(plan,dict(open=2500,low=2400),dict(open=100000,high=110000))
    assert prices == [2500,100000]
    result = settle_legs([dict(quantity=plan['quantity_eth'],entry=3000),
                          dict(quantity=plan['quantity_btc'],entry=90000)],prices,0.00075,0.0005)
    assert -result['pnl'] > plan['risk_budget']+result['slippage_usd']


@pytest.mark.parametrize('beta',[0,-1,float('nan'),float('inf')])
def test_invalid_pair_beta_fails_closed(beta):
    with pytest.raises(ValueError):
        pair_size(10000,3000,90000,beta)


def test_cache_miss_rejects_and_diagnostic_is_explicit():
    kwargs = dict(symbol='BTCUSDT',direction='BUY',entry=100,stop=98,target=104,
                  indicators={'strategy':'ema_trend'},timeout_sec=35)
    engine = RecordedDebateEngine()
    assert engine.deliberate_combined(**kwargs)['verdict'] == 'REJECT'
    assert engine.counts == {'cache_miss':1}
    diagnostic = RecordedDebateEngine(mode='heuristic_diagnostic')
    assert diagnostic.deliberate_combined(**kwargs)['verdict'] == 'APPROVE'
    assert diagnostic.counts == {'heuristic':1}


@pytest.mark.parametrize('override',[dict(conviction_score=float('nan')),dict(latency_ms=35001),
    dict(source='heuristic'),dict(verdict='INVALID'),dict(conviction_score=True),dict(fallback_used=True)])
def test_invalid_recorded_cache_never_falls_back_to_heuristic_approval(override):
    kwargs = dict(symbol='BTCUSDT',direction='BUY',entry=100,stop=98,target=104,indicators={})
    key = debate_key(**kwargs)
    record = dict(source='recorded_model',model='test-fixture-not-a-model-run',verdict='APPROVE',
                  conviction_score=8,latency_ms=1)
    record.update(override)
    engine = RecordedDebateEngine({key:record},mode='heuristic_diagnostic')
    assert engine.deliberate_combined(**kwargs,timeout_sec=35)['verdict'] == 'REJECT'
    assert engine.counts == {'invalid_cache':1}


def test_actual_debate_and_risk_use_fixture_cache_and_enforce_size_cap():
    async def run():
        intent = TradeIntent(symbol='BTCUSDT',entry_price=100,stop_loss=98,take_profit=104,
                             metadata={'debate_context':{'bar_close':1000,'history':'fixture'}})
        indicators = dict(price=100,direction='BUY',stop=98,target=104,strategy='ema_trend',
                          replay_context=intent.metadata['debate_context'])
        key = debate_key('BTCUSDT','BUY',100,98,104,indicators)
        record = dict(source='recorded_model',model='test-fixture-not-a-model-run',verdict='APPROVE',
                      conviction_score=8,latency_ms=1)
        pipeline = ReplayPipeline(records={key:record})
        qty = await pipeline.approve(intent)
        assert qty == 5  # Real RiskBot approves a larger quantity; clamp to its 5% order cap.
        assert pipeline.engine.counts == {'cached':1}
        assert pipeline.summary()['approved'] == 1
        assert pipeline.summary()['size_reductions'] == 0  # Actual RiskBot now applies its own 5% notional cap.
    asyncio.run(run())


def test_real_risk_daily_loss_and_drawdown_halts_trigger_with_counts():
    result = asyncio.run(exercise_risk_halts())
    assert result['daily_loss']['reasons']['DAILY_LOSS_LIMIT'] == 3
    assert result['drawdown']['reasons']['MAX_DRAWDOWN'] == 3
    for row in result.values():
        assert row['risk_pre_veto'] == 3
        assert row['approved'] == 0
        assert not row['debate_sources']


def test_real_risk_correlation_and_position_limits_in_replay_pipeline():
    async def run():
        pipeline = ReplayPipeline(mode='heuristic_diagnostic')
        pipeline.risk.open_positions['BTCUSDT'] = dict(usd_value=500,quantity=5)
        assert await pipeline.approve(TradeIntent(symbol='ETHUSDT',entry_price=100,stop_loss=98,take_profit=104)) is None
        assert pipeline.reasons['CORRELATION_CAP'] == 1
        pipeline.risk.open_positions.update(X=dict(usd_value=10),Y=dict(usd_value=10))
        assert await pipeline.approve(TradeIntent(symbol='SOLUSDT',entry_price=100,stop_loss=98,take_profit=104)) is None
        assert pipeline.reasons['MAX_OPEN_POSITIONS'] == 1
        pair = ReplayPipeline(mode='heuristic_diagnostic')
        assert await pair.approve(TradeIntent(symbol='ETHUSDT',entry_price=100,stop_loss=98,take_profit=104),
            pair_intent=TradeIntent(symbol='BTCUSDT',direction='SELL',entry_price=100,stop_loss=102,take_profit=96)) is None
        assert pair.reasons['CORRELATION_CAP'] == 1
        assert pair.risk.open_positions == {}
    asyncio.run(run())


def test_real_risk_per_coin_exposure_veto_is_counted_post_debate():
    async def run():
        pipeline = ReplayPipeline(mode='heuristic_diagnostic')
        pipeline.risk.open_positions['BTCUSDT'] = dict(usd_value=1500,quantity=15)
        assert await pipeline.approve(TradeIntent(symbol='BTCUSDT',entry_price=100,stop_loss=98,take_profit=104)) is None
        # one position per coin: stacking onto a held coin is now refused before the debate
        assert pipeline.summary()['risk_pre_veto'] == 1
        assert pipeline.reasons['ALREADY_IN_POSITION'] == 1
    asyncio.run(run())


def test_replay_preserves_emergency_fail_closed(tmp_path,monkeypatch):
    monkeypatch.setenv('GOVERNOR_STATE_DB',str(tmp_path/'absent.db'))
    pipeline = ReplayPipeline(mode='heuristic_diagnostic')
    result = asyncio.run(pipeline.approve(TradeIntent(entry_price=100,stop_loss=98,take_profit=104)))
    assert result is None
    assert pipeline.reasons['EMERGENCY_HALT'] == 1


def fixture_candles():
    prices = [100]*51+[90]*6+[100,105,110,120]*10+[100]*23
    rows = []
    for i,price in enumerate(prices):
        opening = prices[i-1] if i else price
        rows.append(dict(open_time=i*3600,close_time=i*3600+3599,open=opening,high=max(price,opening)*1.01,
                         low=min(price,opening)*0.99,close=price,volume=100,taker_buy_volume=60))
    return {s:copy.deepcopy(rows) for s in ('BTCUSDT','ETHUSDT','SOLUSDT')}


def test_future_candles_do_not_change_prior_cache_keys_or_decisions():
    async def run():
        original = fixture_candles()
        changed = copy.deepcopy(original)
        for rows in changed.values():
            for row in rows[100:]:
                for field in ('open','high','low','close'):
                    row[field] *= 3
        before = await replay(original,mode='heuristic_diagnostic',only=('ema_trend','BTCUSDT'))
        after = await replay(changed,mode='heuristic_diagnostic',only=('ema_trend','BTCUSDT'))
        assert before['trades'] and before['debate_request_keys']
        early = lambda r:[t for t in r['trades'] if t['exit_time'] < 100*3600]
        assert early(before) == early(after)
        assert before['debate_request_keys'][0] == after['debate_request_keys'][0]
        assert all(t['entry_time'] > t['signal_time'] for t in before['trades'])
        assert all(t['exit_time'] >= t['entry_time'] for t in before['trades'])
        assert sum(t['pnl'] for t in before['trades']) == pytest.approx(before['metrics']['net_pnl_usd'])
    asyncio.run(run())


def test_archive_is_read_only_and_rejects_gaps(tmp_path):
    import sqlite3
    db = tmp_path/'fixture.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE crypto_candles(symbol,interval,open_time,open,high,low,close,volume,close_time,taker_buy_volume)')
        for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT'):
            for t in (0,7200):
                conn.execute('INSERT INTO crypto_candles VALUES (?,\'1h\',?,100,101,99,100,10,?,5)',(symbol,t,t+3599))
    before = db.read_bytes()
    with pytest.raises(ValueError,match='gap'):
        load_archive(db,count=2)
    assert db.read_bytes() == before


def test_stationarity_windows_are_separate_and_train_is_unchanged_by_future_test_data():
    pytest.importorskip('statsmodels')
    import numpy as np
    from cryptoscope.backtesting.stationarity import stationarity_windows
    rng = np.random.default_rng(17)
    btc = 10+np.cumsum(rng.normal(0,0.01,200))
    eth = 0.8*btc+rng.normal(0,0.005,200)
    store = {s:[dict(close=float(math.exp(p)),open_time=i*3600,close_time=i*3600+3599)
                for i,p in enumerate(prices)] for s,prices in [('ETHUSDT',eth),('BTCUSDT',btc)]}
    changed = copy.deepcopy(store)
    for i,row in enumerate(changed['ETHUSDT'][140:]):
        row['close'] *= math.exp(i/100)
    original,altered = stationarity_windows(store),stationarity_windows(changed)
    assert original['windows']['TRAIN'] == altered['windows']['TRAIN']
    assert original['windows']['TEST'] != altered['windows']['TEST']
    assert original['windows']['TRAIN']['bars'] == 140
    assert original['windows']['TEST']['bars'] == 60
