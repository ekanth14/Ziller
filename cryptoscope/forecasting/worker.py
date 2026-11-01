"""Local-only inference entry point in the isolated torch environment."""
import argparse
from contextlib import redirect_stdout
import json
import sys
import time
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.forecasting import snapshot_hash, validate_forecast
from cryptoscope.research.settings import ROOT


def infer(snapshot, steps=12, samples=3, seed=42):
    if type(steps) is not int or not 1 <= steps <= 96 or type(samples) is not int or not 1 <= samples <= 16:
        raise ValueError('steps must be 1..96 and samples must be 1..16')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('seed must be an unsigned 32-bit integer')
    if snapshot.as_of > time.time()+1:
        raise ValueError('Future input refused')
    import numpy as np
    import pandas as pd
    import torch
    sys.path.insert(0, str(ROOT/'integrations/kronos/vendor'))
    from model import Kronos, KronosTokenizer, KronosPredictor
    model_root = ROOT/'data/models/kronos'
    manifest = json.loads((model_root/'manifest.json').read_text(encoding='utf-8'))
    torch.set_num_threads(4)
    torch.manual_seed(seed)
    np.random.seed(seed)
    with redirect_stdout(sys.stderr):
        tokenizer = KronosTokenizer.from_pretrained(str(model_root/'tokenizer'), local_files_only=True)
        model = Kronos.from_pretrained(str(model_root/'model'), local_files_only=True)
        model.eval()
        tokenizer.eval()
        predictor = KronosPredictor(model, tokenizer, device='cpu', max_context=512)
        candles = snapshot.candles[-512:]
        df = pd.DataFrame(candles)[['open','high','low','close','volume']]
        # Quote turnover is unavailable in older snapshots. Let the reviewed
        # predictor derive its documented OHLC-mean * base-volume proxy.
        x = pd.Series(pd.to_datetime([c['open_time'] for c in candles],unit='s',utc=True).tz_localize(None))
        start = candles[-1]['close_time']
        times = [start+i*snapshot.interval_seconds for i in range(steps)]
        y = pd.Series(pd.to_datetime(times,unit='s',utc=True).tz_localize(None))
        with torch.inference_mode():
            predicted = predictor.predict(df, x, y, steps, T=1.0, top_p=.9, sample_count=samples, verbose=False)
    rows = [{'open_time':stamp, **{key:float(predicted.iloc[i][key]) for key in ('open','high','low','close')}} for i,stamp in enumerate(times)]
    report = {'kind':'forecast', 'status':'completed', 'symbol':snapshot.symbol,
        'source':snapshot.source, 'model':'NeoQuasar/Kronos-small', 'model_revisions':manifest,
        'input_hash':snapshot_hash(snapshot), 'input_cutoff':snapshot.as_of,
        'input_last_close_time':snapshot.candles[-1]['close_time'],
        'interval_seconds':snapshot.interval_seconds, 'context_bars':len(candles),
        'available_at':time.time(), 'forecast':rows,
        'parameters':{'steps':steps,'samples':samples,'seed':seed,'temperature':1.0,'top_p':.9},
        'volume_amount_policy':'base volume; amount approximated by mean OHLC times volume',
        'decision_source':'forecast_only_not_laya', 'network_requests':0}
    return validate_forecast(report,snapshot)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--steps',type=int,default=12)
    parser.add_argument('--samples',type=int,default=3)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    try:
        report=infer(Snapshot.parse(json.load(sys.stdin)),args.steps,args.samples,args.seed)
        print(json.dumps(report,allow_nan=False))
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        raise SystemExit(1)
