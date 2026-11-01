"""Causal strategy candidates and deterministic trade levels."""
import time
from cryptoscope.agents.analysts.market import technical, ema
from cryptoscope.agents.schemas import Proposal


def analyze(snapshot):
    indicators=technical(snapshot)
    bars=snapshot.candles
    close=indicators['close']
    rsi=indicators['rsi14']
    previous=bars[-21:-1]
    high=max(c['high'] for c in previous)
    volume=sum(c['volume'] for c in previous)/len(previous)

    # Multi-timeframe confirmation (aggregate 3 consecutive closed bars for higher timeframe trend)
    htf_bars=[]
    k=3
    for i in range(0,len(bars)-(len(bars)%k),k):
        chunk=bars[i:i+k]
        htf_bars.append({'open':chunk[0]['open'],'high':max(c['high'] for c in chunk),
                         'low':min(c['low'] for c in chunk),'close':chunk[-1]['close'],
                         'volume':sum(c['volume'] for c in chunk)})
    htf_closes=[b['close'] for b in htf_bars] if len(htf_bars)>=20 else []
    htf_trend=False
    if len(htf_closes)>=20:
        htf_ema10=ema(htf_closes,10)
        htf_ema20=ema(htf_closes,20)
        htf_trend=htf_ema10>htf_ema20 and htf_closes[-1]>=htf_ema10

    # Volatility squeeze: Bollinger Bands vs Keltner Channels + volume expansion
    recent_closes=[c['close'] for c in bars[-20:]]
    mean20=sum(recent_closes)/20
    std20=(sum((x-mean20)**2 for x in recent_closes)/20)**0.5
    upper_bb=mean20+2.0*std20
    upper_keltner=indicators['ema20']+1.5*indicators['atr14']
    squeeze_expansion=(close>=upper_bb or close>=upper_keltner) and bars[-1]['volume']>=volume and 50<=rsi<75

    # MACD momentum cross: 12/26 EMA line crossing 9 EMA signal with positive slope
    closes=[c['close'] for c in bars]
    macd_history=[ema(closes[:len(closes)-i],12)-ema(closes[:len(closes)-i],26) for i in reversed(range(10))] if len(closes)>=35 else []
    macd_signal=ema(macd_history,9) if len(macd_history)>=9 else 0.0
    macd_cross=len(macd_history)>=9 and macd_history[-1]>macd_signal and macd_history[-1]>0 and close>=indicators['ema20'] and 45<=rsi<70

    # SMC Order Block demand zone test with buying reaction
    order_blocks=indicators.get('order_blocks',[])
    bullish_obs=[ob for ob in order_blocks if ob['type']=='BULLISH_OB']
    smc_rebound=False
    if bullish_obs:
        latest_ob=bullish_obs[-1]
        smc_rebound=(latest_ob['low']*0.998<=close<=latest_ob['high']*1.015) and close>bars[-2]['close'] and rsi>=40

    checks={
        'ema_trend':indicators['ema20']>indicators['ema50'] and close>=indicators['ema20'] and 45<=rsi<70,
        'mtf_confirmation':htf_trend and indicators['ema20']>indicators['ema50'] and close>=indicators['ema20'] and 45<=rsi<70,
        'volatility_squeeze':squeeze_expansion,
        'macd_momentum_cross':macd_cross,
        'smc_order_block':smc_rebound,
        'rsi_rebound':rsi<30 and close>bars[-2]['close'],
        'volume_breakout':close>high and bars[-1]['volume']>=1.2*volume and rsi<75,
    }
    return {'indicators':{k:round(indicators[k],8) for k in ('close','ema20','ema50','rsi14','atr14')},
        'candidates':[key for key,active in checks.items() if active],
        'signals':checks,'previous_high20':high,
        'order_blocks':order_blocks,
        'directional_score':indicators.get('directional_score',0.0),
        'setup':indicators.get('setup','NEUTRAL'),
        'exit_context':{'trend_reversal':indicators['ema20']<indicators['ema50'] and close<indicators['ema20'],
                        'overbought':rsi>=75}}


def context(snapshot, analysis, portfolio, quote):
    held=portfolio['positions'].get(snapshot.symbol)
    candidates=analysis['candidates']
    actions=['HOLD']+(['SELL'] if held else ['BUY'] if candidates and not portfolio['positions'] else [])
    strategies=['none']+(['position_exit'] if held else candidates if 'BUY' in actions else [])
    return {'symbol':snapshot.symbol,'indicators':analysis['indicators'],'candidates':candidates,
        'exit_context':analysis['exit_context'],'position':held,
        'bid':quote['bid'],'ask':quote['ask'],'allowed_actions':actions,'allowed_strategies':strategies,
        'missing_sources':['news','derivatives']}


def proposal(decision, snapshot, analysis, quote, settings, risk, now=None):
    now=time.time() if now is None else now
    action=decision['action']
    reason=decision.get('reason',f"Laya selected {action} using {decision['strategy']}")
    if action=='HOLD':
        if decision['strategy']!='none':
            raise ValueError('HOLD requires strategy none')
        return None
    if action=='SELL':
        if decision['strategy']!='position_exit':
            raise ValueError('SELL requires position_exit')
        return Proposal.parse({'action':'CLOSE','symbol':snapshot.symbol,'entry':None,'stop':None,'target':None,
            'confidence':0,'thesis':reason,'evidence':['technical'],'expires_at':now+30,'reduce_fraction':1},snapshot.symbol)
    if action!='BUY' or decision['strategy'] not in analysis['candidates']:
        raise ValueError('BUY must select an active strategy candidate')
    expected=quote['ask']*(1+risk['slippage_fraction'])
    distance=max(analysis['indicators']['atr14']*settings['stop_atr_multiple'],
                 expected*settings['minimum_stop_fraction'])
    if distance/expected>settings['maximum_stop_fraction']:
        raise ValueError('Volatility requires a stop wider than the configured limit')
    stop=expected-distance
    fees=risk['fee_fraction']
    stop_fill=stop*(1-risk['slippage_fraction'])
    loss=expected-stop_fill+fees*(expected+stop_fill)
    # Solve the same fee/slippage equation used by the execution gate.
    target=(settings['target_reward_risk']*loss+expected*(1+fees))/((1-risk['slippage_fraction'])*(1-fees))
    return Proposal.parse({'action':'LONG','symbol':snapshot.symbol,'entry':quote['ask'],
        'stop':stop,'target':target,'confidence':0,'thesis':reason,'evidence':['technical'],
        'expires_at':now+30,'reduce_fraction':1},snapshot.symbol)
