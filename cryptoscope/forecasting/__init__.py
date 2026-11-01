"""Optional Kronos evidence; the research model remains Laya."""
import hashlib
import json
import subprocess
import time
from cryptoscope.agents.schemas import number
from cryptoscope.research.settings import ROOT


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot.to_dict(), sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_forecast(report, snapshot, now=None):
    now = time.time() if now is None else now
    if not isinstance(report, dict) or report.get('status') != 'completed':
        raise ValueError('Kronos did not complete successfully')
    if report.get('input_hash') != snapshot_hash(snapshot) or report.get('symbol') != snapshot.symbol:
        raise ValueError('Forecast does not belong to this snapshot')
    if report.get('input_cutoff') != snapshot.as_of:
        raise ValueError('Forecast cutoff differs from input snapshot')
    available = number(report.get('available_at'), 'forecast availability', 1)
    if available > now + 1 or available < snapshot.as_of:
        raise ValueError('Invalid forecast availability time')
    bars = report.get('forecast', [])
    steps = report.get('parameters', {}).get('steps')
    if type(steps) is not int or not 1 <= steps <= 96 or len(bars) != steps:
        raise ValueError('Invalid forecast horizon')
    start = snapshot.candles[-1]['close_time']
    for index, bar in enumerate(bars):
        if bar.get('open_time') != start + index * snapshot.interval_seconds:
            raise ValueError('Forecast timestamps are not contiguous future bars')
        for key in ('open','high','low','close'):
            number(bar.get(key), key, 0.00000001)
        if not bar['low'] <= min(bar['open'],bar['close']) <= max(bar['open'],bar['close']) <= bar['high']:
            raise ValueError('Kronos generated inconsistent OHLC values')
    return report


def forecast(snapshot, steps=12, samples=3, seed=42, timeout=300):
    executable = ROOT/'work/environments/kronos/Scripts/python.exe'
    if not executable.exists():
        raise RuntimeError('Install the optional Kronos environment with scripts/setup-kronos.ps1')
    process = subprocess.run([str(executable), '-B', '-m', 'cryptoscope.forecasting.worker',
        '--steps', str(steps), '--samples', str(samples), '--seed', str(seed)],
        input=json.dumps(snapshot.to_dict(), allow_nan=False), text=True, capture_output=True,
        cwd=ROOT, timeout=timeout)
    if process.returncode:
        raise RuntimeError('Kronos inference failed: '+process.stderr[-1500:])
    return validate_forecast(json.loads(process.stdout), snapshot)


def evidence(report, snapshot):
    validate_forecast(report, snapshot)
    last = snapshot.candles[-1]['close']
    return {'id':'kronos', 'status':'available', 'model':report['model'],
        'available_at':report['available_at'], 'input_cutoff':snapshot.as_of,
        'horizon_bars':len(report['forecast']), 'last_observed_close':last,
        'projected_final_close':report['forecast'][-1]['close'],
        'projected_change_pct':100*(report['forecast'][-1]['close']/last-1),
        'warnings':['A sampled model forecast is not a calibrated probability or an execution instruction.',
                    'Inference availability is later than the input cutoff; do not backdate this evidence.']}
