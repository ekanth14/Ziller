import json
from pathlib import Path
from cryptoscope.agents.schemas import number
from cryptoscope.providers.binance import INTERVALS
from cryptoscope.research.settings import ROOT, load_config


def load_settings(path=None):
    settings=json.loads((ROOT/'config/autotrader.json').read_text(encoding='utf-8'))
    if path:
        overrides=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(overrides,dict) or set(overrides)-set(settings):
            raise ValueError('Autotrader config contains unsupported keys')
        settings.update(overrides)
    if settings['mode']!='paper':
        raise ValueError('This bot supports paper trading only')
    if settings['interval'] not in INTERVALS:
        raise ValueError('Unsupported candle interval')
    base=load_config()
    symbols=settings['symbols']
    if not isinstance(symbols,list) or not symbols or len(symbols)>10 or len(set(symbols))!=len(symbols) or any(s not in base['symbols'] for s in symbols):
        raise ValueError('Autotrader symbols must be unique members of the research universe')
    for key in ('daily_loss_fraction','drawdown_fraction','max_spread_fraction','risk_fraction',
                'max_position_fraction','minimum_stop_fraction','maximum_stop_fraction'):
        if not 0<number(settings[key],key)<1:
            raise ValueError(key+' must be between zero and one')
    for key in ('quote_poll_seconds','snapshot_poll_seconds','model_timeout_seconds','decision_max_age_seconds',
                'max_snapshot_age_seconds','max_quote_age_seconds','cooldown_seconds','stop_atr_multiple',
                'trailing_atr_multiple','target_reward_risk'):
        number(settings[key],key,.000001)
    if settings['quote_poll_seconds']<1 or settings['snapshot_poll_seconds']<5 or settings['model_timeout_seconds']>120:
        raise ValueError('Polling or inference limits are invalid')
    if type(settings['max_entries_per_day']) is not int or not 1<=settings['max_entries_per_day']<=100:
        raise ValueError('max_entries_per_day must be 1..100')
    if settings['minimum_stop_fraction']>=settings['maximum_stop_fraction'] or settings['target_reward_risk']<base['minimum_reward_risk']:
        raise ValueError('Invalid stop or reward/risk limits')
    risk={**base,**{k:settings[k] for k in ('symbols','interval','risk_fraction','max_position_fraction',
          'max_snapshot_age_seconds','max_quote_age_seconds')}}
    inference={**risk,'model_timeout_seconds':settings['model_timeout_seconds'],
        'model_max_output_tokens':48,'model_thinking':False,'model_context_tokens':4096,
        'model_keep_alive':'15m','model_retry_invalid_output':False}
    return settings,risk,inference
