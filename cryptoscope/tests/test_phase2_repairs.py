"""Regressions for Phase 2 model protocol, real risk sizing and portfolio marks."""
import asyncio
import json
from unittest.mock import MagicMock,patch

import pytest

from cryptoscope.backtesting.compact_debate import CompactDebateEngine
from cryptoscope.backtesting.fleet_replay import ReplayPipeline
from cryptoscope.orchestrator.events import TradeIntent,DebateResult,RiskDecision,Fill
from cryptoscope.backtesting.integrity import pair_size,pair_stop_prices,trade_metrics
from cryptoscope.backtesting.pair_audit import gap_sensitivity


def generate(body):
    request=dict(symbol='BTCUSDT',direction='BUY',entry=100,stop=98,target=104,
                 indicators={'strategy':'ema_trend'},model='fixture',timeout_sec=35)
    with patch('cryptoscope.backtesting.compact_debate.post_json_deadline',return_value=body) as opened:
        result=CompactDebateEngine().deliberate_combined(**request)
        payload=opened.call_args.args[1]
    assert payload['raw'] is True and payload['think'] is False
    assert payload['options']['num_predict']==40
    return result


def test_compact_committee_uses_real_returned_scores_without_sizing_fields():
    result=generate(dict(done=True,done_reason='stop',response=json.dumps(dict(bull=8,bear=4,risk=7,vote=1))))
    assert result['verdict']=='APPROVE' and result['conviction_score']==7
    assert result['committee_scores']==dict(bull=8,bear=4,risk=7,vote=1)
    assert not any(k in result for k in ('quantity','risk_budget','size'))


@pytest.mark.parametrize('body',[
    [],
    dict(done=False,response='{}'),dict(done=True,done_reason='length',response='{}'),
    dict(done=True,done_reason='stop',response='bad json'),
    dict(done=True,done_reason='stop',response='{"bull":9,"bear":1,"risk":true,"vote":1}'),
    dict(done=True,done_reason='stop',response='{"bull":9,"bear":1,"risk":7,"vote":1,"size":100}')])
def test_incomplete_invalid_or_extra_model_fields_fail_closed_with_category(body):
    result=generate(body)
    assert result['fallback_used'] and result['verdict']=='REJECT'
    assert result['failure_category'] in {'invalid_json','invalid_or_incomplete_output'}


def test_timeout_has_safe_typed_failure_record():
    with patch('cryptoscope.backtesting.compact_debate.post_json_deadline',side_effect=TimeoutError('private text')):
        result=CompactDebateEngine().deliberate_combined(symbol='BTCUSDT',direction='BUY',entry=100,
            stop=98,target=104,indicators={},model='fixture',timeout_sec=35)
    assert result['failure_category']=='timeout' and result['verdict']=='REJECT'
    assert 'private text' not in json.dumps(result)


def test_complete_but_late_vote_is_still_rejected():
    with patch('cryptoscope.backtesting.compact_debate.time.perf_counter',side_effect=[0,36,36]):
        result=generate(dict(done=True,done_reason='stop',response=json.dumps(dict(bull=8,bear=4,risk=7,vote=1))))
    assert result['failure_category']=='timeout' and result['verdict']=='REJECT'


def test_cash_realization_does_not_create_false_portfolio_peak():
    async def run():
        pipeline=ReplayPipeline()
        pipeline.risk.peak_nav=10000
        pipeline.risk.current_nav=10000
        await pipeline.closed({'symbols':['BTCUSDT'],'pnl':100})
        assert pipeline.risk.current_nav==10100
        assert pipeline.risk.peak_nav==10000
        pipeline.mark(9900,0)  # Includes another position's unrealized loss.
        assert pipeline.risk.peak_nav==10000
    asyncio.run(run())


def test_atomic_pair_with_relaxed_matrix_still_cannot_short_spot():
    async def run():
        pipeline=ReplayPipeline(mode='heuristic_diagnostic')
        pipeline.risk.correlation_matrix={}
        assert await pipeline.approve(TradeIntent(symbol='ETHUSDT',entry_price=100,stop_loss=98,take_profit=104),
            pair_intent=TradeIntent(symbol='BTCUSDT',direction='SELL',entry_price=100,stop_loss=102,take_profit=96)) is None
        assert pipeline.reasons['PAIR_SHORT_UNSUPPORTED_SPOT']==1
        assert pipeline.summary()['approved']==0
    asyncio.run(run())


@pytest.mark.parametrize('entry,stop,target',[(0,98,104),(float('nan'),98,104),(100,102,104),(100,98,float('inf'))])
def test_actual_risk_vetoes_invalid_bracket_without_exception(entry,stop,target):
    async def run():
        pipeline=ReplayPipeline()
        intent=TradeIntent(symbol='BTCUSDT',entry_price=entry,stop_loss=stop,take_profit=target)
        passed,reasons=pipeline.risk.check_pre_trade_risk(intent)
        assert not passed and 'INVALID_PRICES' in reasons[0]
        await pipeline.risk.on_event(intent)
        await pipeline.risk._evaluate_risk(DebateResult(intent_id=intent.intent_id,verdict='APPROVE'))
        assert pipeline.decisions[0].decision=='VETOED'
    asyncio.run(run())


def test_actual_risk_notional_cap_and_partial_exit_exposure():
    async def run():
        pipeline=ReplayPipeline()
        intent=TradeIntent(symbol='BTCUSDT',entry_price=123.4567,stop_loss=120,take_profit=130)
        await pipeline.risk.on_event(intent)
        await pipeline.risk._evaluate_risk(DebateResult(intent_id=intent.intent_id,verdict='APPROVE'))
        decision=pipeline.decisions[0]
        assert decision.decision=='APPROVED'
        assert decision.approved_quantity*intent.entry_price<=500
        assert decision.risk_usd==pytest.approx(round(decision.approved_quantity*3.4567,2))
        await pipeline.risk.on_event(Fill(symbol='BTCUSDT',side='BUY',quantity=4,executed_price=100))
        await pipeline.risk.on_event(Fill(symbol='BTCUSDT',side='SELL',quantity=1,executed_price=110))
        assert pipeline.risk.open_positions['BTCUSDT']['usd_value']==300
    asyncio.run(run())


def test_pair_exit_never_invents_hedge_prices_outside_observed_bar():
    plan=pair_size(10000,3000,90000,1)
    assert pair_stop_prices(plan,{'open':3000,'low':2900},{'open':90000,'high':90500})==[2940,90500]
    assert pair_stop_prices(plan,{'open':3000,'low':2990},{'open':90000,'high':93000})==[2990,91800]


def test_predeclared_gap_grid_reports_excess_instead_of_clipping_losses():
    rows=gap_sensitivity()
    assert len(rows)==12
    assert all(r['excess_usd']<1e-8 for r in rows if r['adverse_gap']==0)
    assert all(r['excess_usd']>0 for r in rows if r['adverse_gap']>0)


@pytest.mark.parametrize('capital,pnl',[(0,1),(float('inf'),1),(10000,float('nan'))])
def test_invalid_performance_inputs_are_rejected(capital,pnl):
    with pytest.raises(ValueError):trade_metrics([{'pnl':pnl}],capital)


def test_actual_portfolio_limit_exercises_reconcile_counts():
    from cryptoscope.backtesting.risk_exercises import exercise_portfolio_limits
    result=asyncio.run(exercise_portfolio_limits())
    assert result['correlation']['reasons']['CORRELATION_CAP']==1
    assert result['position_count']['reasons']['MAX_OPEN_POSITIONS']==1
    assert result['per_coin']['reasons']['EXPOSURE_CAP']==1
    assert result['per_coin']['risk_post_veto']==1
    assert result['order_notional']['approved_quantity']==5


def test_drawdown_halt_survives_market_recovery_and_day_rollover():
    async def run():
        pipeline=ReplayPipeline(mode='heuristic_diagnostic')
        pipeline.mark(8900,0)
        assert pipeline.risk.drawdown_circuit_breaker
        pipeline.mark(10100,86400)
        assert pipeline.risk.drawdown_circuit_breaker
        assert await pipeline.approve(TradeIntent(entry_price=100,stop_loss=98,take_profit=104)) is None
        assert pipeline.reasons['MAX_DRAWDOWN']==1
    asyncio.run(run())
