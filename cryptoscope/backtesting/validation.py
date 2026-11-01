"""Chronological validation and descriptive robustness checks, not deployment approval."""
import hashlib
import json
import math
import random
import statistics
from cryptoscope.agents.schemas import Snapshot


def performance(navs, initial_cash, interval_seconds):
    returns=[]
    previous=initial_cash
    for nav in navs:
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError('Equity values must be finite and positive')
        returns.append(nav/previous-1)
        previous=nav
    annual_bars=365*86400/interval_seconds
    std=statistics.stdev(returns) if len(returns)>1 else 0
    mean=statistics.mean(returns)
    downside=math.sqrt(sum(min(r,0)**2 for r in returns)/len(returns))
    return {'annual_bars':annual_bars, 'observations':len(returns),
        'sharpe_zero_rf':mean/std*math.sqrt(annual_bars) if std>1e-15 else None,
        'sortino_zero_rf':mean/downside*math.sqrt(annual_bars) if downside>1e-15 else None,
        'annualized_volatility_pct':std*math.sqrt(annual_bars)*100,
        'assumptions':'365-day crypto calendar; zero risk-free rate; descriptive annualization, not statistical significance.'}


def bootstrap(navs, initial_cash, paths=250, block_length=8, seed=42):
    if type(paths) is not int or not 10 <= paths <= 2000 or type(block_length) is not int or block_length<1:
        raise ValueError('Invalid bootstrap limits')
    changes=[]
    previous=initial_cash
    for nav in navs:
        if not math.isfinite(nav) or nav<=0:
            raise ValueError('Equity values must be finite and positive')
        changes.append(nav/previous-1)
        previous=nav
    if len(changes)<2:
        raise ValueError('At least two equity observations required')
    rng=random.Random(seed)
    outcomes=[]
    for _ in range(paths):
        resampled=[]
        while len(resampled)<len(changes):
            start=rng.randrange(len(changes))
            resampled.extend(changes[(start+j)%len(changes)] for j in range(min(block_length,len(changes))))
        outcomes.append(100*(math.prod(1+r for r in resampled[:len(changes)])-1))
    outcomes.sort()
    def quantile(p):
        offset=p*(len(outcomes)-1)
        low=int(offset)
        high=min(low+1,len(outcomes)-1)
        return outcomes[low]+(outcomes[high]-outcomes[low])*(offset-low)
    return {'method':'circular_moving_block_bootstrap', 'paths':paths, 'block_length':min(block_length,len(changes)),
        'seed':seed, 'return_pct_p05':quantile(.05), 'return_pct_median':quantile(.5),
        'return_pct_p95':quantile(.95), 'empirical_loss_fraction':sum(x<0 for x in outcomes)/paths,
        'limitations':'Resamples observed net returns; not a forecast probability, confidence guarantee or new market-regime simulation.'}


def subset(snapshot, start, end):
    candles=snapshot.candles[start:end]
    return Snapshot.parse({**snapshot.to_dict(), 'candles':candles, 'as_of':candles[-1]['close_time'],
                           'derivatives':{},'news':[]})


def walk_forward(snapshot, config, train_bars=100, test_bars=40, embargo_bars=2, candidates=None):
    from cryptoscope.backtesting.runner import evaluate
    candidates=[(5,15),(10,30),(20,50)] if candidates is None else candidates
    if any(type(x) is not int for x in (train_bars,test_bars,embargo_bars)) or train_bars<55 or test_bars<3 or embargo_bars<1:
        raise ValueError('Need train >=55, test >=3, and embargo >=1 closed bars')
    if len(candidates)>25 or not candidates:
        raise ValueError('Use 1..25 predeclared EMA candidates')
    for fast,slow in candidates:
        if type(fast) is not int or type(slow) is not int or not 1<fast<slow<train_bars-2:
            raise ValueError('Candidate periods do not fit the training window')
    folds=[]
    combined=[]
    total_fills=0
    total_fees=0
    fills=[]
    decisions=[]
    capital=config['initial_cash']
    train_start=0
    peak=capital
    max_drawdown=0
    while train_start+train_bars+embargo_bars+test_bars<=len(snapshot.candles):
        train_end=train_start+train_bars
        test_start=train_end+embargo_bars
        test_end=test_start+test_bars
        training=subset(snapshot,train_start,train_end)
        trials=[]
        for fast,slow in candidates:
            result=evaluate(training,config,fast,slow,diagnostics=False)
            trials.append({'fast':fast,'slow':slow,'net_return_pct':result['metrics']['net_return_pct']})
        selected=max(trials,key=lambda row:(row['net_return_pct'],-row['slow'],-row['fast']))
        # Prior bars initialize causal EMAs but cannot create positions before
        # the test boundary. Training labels and trades end before the embargo.
        warmup=max(50,selected['slow'])
        test=subset(snapshot,test_start-warmup,test_end)
        result=evaluate(test,config,selected['fast'],selected['slow'],start_index=warmup,diagnostics=False)
        scale=capital/config['initial_cash']
        for row in result['equity'][warmup:]:
            nav=row['nav']*scale
            peak=max(peak,nav)
            drawdown=100*(peak-nav)/peak
            max_drawdown=max(max_drawdown,drawdown)
            combined.append({**row,'nav':nav,'cash':row['cash']*scale,'position':row['position']*scale,'drawdown_pct':drawdown})
        capital=combined[-1]['nav']
        fills.extend({**fill,'quantity':fill['quantity']*scale,'fee':fill['fee']*scale,
                      'notional':fill['notional']*scale,'fold':len(folds)+1} for fill in result['fills'])
        decisions.extend({**row,'quantity':row['quantity']*scale,'fold':len(folds)+1} for row in result['decisions'])
        total_fees+=result['metrics']['fees']*scale
        total_fills+=result['metrics']['fills']
        folds.append({'train_start':training.candles[0]['open_time'],
            'train_end':training.candles[-1]['close_time'],
            'test_start':snapshot.candles[test_start]['open_time'],
            'test_end':snapshot.candles[test_end-1]['close_time'],
            'selected':selected,'trials':trials,'test_metrics':result['metrics']})
        train_start+=test_bars
    if not folds:
        raise ValueError('Snapshot is too short for one complete walk-forward fold')
    settings={k:config[k] for k in ('initial_cash','max_position_fraction','fee_fraction','slippage_fraction')}
    parameters={'train_bars':train_bars,'test_bars':test_bars,'embargo_bars':embargo_bars,'candidates':candidates}
    fingerprint=hashlib.sha256(json.dumps({'snapshot':snapshot.to_dict(),'settings':settings,
        'parameters':parameters,'method':'rolling_walk_forward_ema_v1'},sort_keys=True,allow_nan=False).encode()).hexdigest()
    navs=[r['nav'] for r in combined]
    return {'kind':'backtest','status':'completed','strategy':'walk_forward_ema',
        'decision_source':'deterministic_baseline_not_laya','symbol':snapshot.symbol,'source':snapshot.source,
        'engine':'quantjourney-bt','engine_version':result['engine_version'],
        'fingerprint':fingerprint,'settings':settings,'parameters':parameters,
        'interval_seconds':snapshot.interval_seconds,'period_start':folds[0]['test_start'],'period_end':folds[-1]['test_end'],
        'metrics':{'initial_cash':config['initial_cash'],'final_nav':capital,
            'net_return_pct':100*(capital/config['initial_cash']-1),'max_drawdown_pct':max_drawdown,
            'fees':total_fees,'fills':total_fills,'folds':len(folds)},
        'equity':combined,'fills':fills,'decisions':decisions,'folds':folds,
        'performance':performance(navs,config['initial_cash'],snapshot.interval_seconds),
        'bootstrap':bootstrap(navs,config['initial_cash']),
        'limitations':['Template EMA baseline validation, not historical Laya or Kronos evaluation.',
            'Training uses net return to select from a predeclared finite grid; multiple-testing bias remains.',
            'Independent flat fold accounts are compounded; each fold liquidates at its final open.',
            'Only complete non-overlapping test windows are included; unused tail bars are excluded.',
            'A short candle archive cannot establish robustness across market regimes.']}


def robustness(snapshot, config, fast=20, slow=50):
    from cryptoscope.backtesting.runner import evaluate
    baseline=evaluate(snapshot,config,fast,slow,diagnostics=False)
    comparison=evaluate(snapshot,config,fast,slow,strategy='buy_hold_baseline',diagnostics=False)
    sensitivity=[]
    for multiplier in (1,2,3):
        stressed={**config,'fee_fraction':config['fee_fraction']*multiplier,
                  'slippage_fraction':config['slippage_fraction']*multiplier}
        if max(stressed['fee_fraction'],stressed['slippage_fraction'])>=1:
            raise ValueError('Stressed transaction cost must be less than one')
        report=baseline if multiplier==1 else evaluate(snapshot,stressed,fast,slow,diagnostics=False)
        sensitivity.append({'cost_multiplier':multiplier,'fee_fraction':stressed['fee_fraction'],
            'slippage_fraction':stressed['slippage_fraction'],'metrics':report['metrics']})
    baseline['strategy']='ema_robustness'
    baseline['comparison']={'strategy':'buy_hold_baseline','metrics':comparison['metrics'],
        'policy':'Same capital, warmup, position cap, next-bar execution and costs as the EMA baseline.'}
    baseline['cost_sensitivity']=sensitivity
    baseline['bootstrap']=bootstrap([r['nav'] for r in baseline['equity']],config['initial_cash'])
    baseline['fingerprint']=hashlib.sha256((baseline['fingerprint']+':robustness_v1').encode()).hexdigest()
    return baseline
