"""Deterministic scenarios exercising real RiskBot halts, not market evidence."""
from cryptoscope.backtesting.fleet_replay import ReplayPipeline
from cryptoscope.orchestrator.events import PositionClosed,TradeIntent


async def exercise_risk_halts():
    results = {}
    for name in ('daily_loss','drawdown'):
        pipeline = ReplayPipeline(mode='heuristic_diagnostic')
        count = 3 if name == 'daily_loss' else 10
        loss = -110.0
        for i in range(count):
            timestamp = i*86400 if name == 'drawdown' else 0
            pipeline.mark(pipeline.risk.current_nav,timestamp)
            await pipeline.risk.on_event(PositionClosed(symbol='SOLUSDT',pnl_usd=loss))
        if name == 'drawdown':
            pipeline.mark(pipeline.risk.current_nav,count*86400)
        for _ in range(3):
            await pipeline.approve(TradeIntent(symbol='BTCUSDT',entry_price=100,
                                             stop_loss=98,take_profit=104))
        results[name] = dict(pipeline.summary(),closed_loss_events=count,
                            nav=pipeline.risk.current_nav,daily_pnl=pipeline.risk.daily_realized_pnl)
    return results


async def exercise_portfolio_limits():
    """Synthetic control proofs, with actual pre/post risk stage counts."""
    results={}
    for name in ('correlation','position_count','per_coin','order_notional'):
        pipeline=ReplayPipeline(mode='heuristic_diagnostic')
        symbol='BTCUSDT'
        if name=='correlation':
            pipeline.risk.open_positions['BTCUSDT']=dict(quantity=5,usd_value=500)
            symbol='ETHUSDT'
        elif name=='position_count':
            pipeline.risk.open_positions={s:dict(quantity=1,usd_value=100) for s in ('A','B','C')}
        elif name=='per_coin':
            pipeline.risk.open_positions['BTCUSDT']=dict(quantity=15,usd_value=1500)
        quantity=await pipeline.approve(TradeIntent(symbol=symbol,entry_price=100,stop_loss=98,take_profit=104))
        results[name]=dict(pipeline.summary(),approved_quantity=quantity)
    return results
