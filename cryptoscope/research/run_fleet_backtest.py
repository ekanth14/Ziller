"""Offline Phase 2 research CLI. Launch with scripts/run_phase2_research.py.

All outputs are new files in a retained disposable copy. No production candle
cache mutation, downloads, order clients or model generation are permitted.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from cryptoscope.backtesting.fleet_replay import FROZEN_PARAMETERS,load_archive,data_fingerprint,replay
from cryptoscope.backtesting.integrity import trade_metrics
from cryptoscope.backtesting.legacy_audit import audit_legacy
from cryptoscope.backtesting.pair_audit import audit_pair_stops
from cryptoscope.backtesting.risk_exercises import exercise_risk_halts
from cryptoscope.backtesting.stationarity import stationarity_windows
from cryptoscope.security.halt_state import GovernorState


async def research(args):
    sandbox = Path(os.environ['ZILLERS_AUDIT_SANDBOX']).resolve()
    store = load_archive(sandbox/'work/runtime/crypto_candles.db')
    state_path = sandbox/'tmp/research-governor.db'
    os.environ['GOVERNOR_STATE_DB'] = str(state_path)
    GovernorState(state_path).resume_local_admin(admin_reauthenticated=True,actor='disposable-research-admin')
    records = {}
    if args.cache:
        records = json.loads(Path(args.cache).read_text(encoding='utf-8'))['records']
    result = dict(parameters=FROZEN_PARAMETERS,parameters_frozen_before_run=True,
                  dataset=dict(fingerprint=data_fingerprint(store),bars_per_symbol=2160,
                               start=store['BTCUSDT'][0]['open_time'],end=store['BTCUSDT'][-1]['close_time'],
                               train_bars=1512,test_bars=648,ordering_gaps_alignment='PASS'),
                  cache=dict(record_count=len(records),source='user-supplied' if args.cache else 'no exact recorded cache found'),
                  shared_account={},comparison_books=[],pair_stop_audit={},risk_exercises=await exercise_risk_halts())
    for split,lo,hi in [('TRAIN',0,1512),('TEST',1512,2160)]:
        window = {s:bars[lo:hi] for s,bars in store.items()}
        result['shared_account'][split] = {}
        for mode in ('recorded','heuristic_diagnostic'):
            result['shared_account'][split][mode] = await replay(window,mode=mode,records=records)
        for symbol in ('BTCUSDT','ETHUSDT','SOLUSDT'):
            for strategy in ('ema_trend','volatility_breakout'):
                book = await replay(window,mode='heuristic_diagnostic',records=records,only=(strategy,symbol))
                result['comparison_books'].append(dict(book,split=split,strategy=strategy,symbol=symbol))
        book = await replay(window,mode='heuristic_diagnostic',records=records,only=('stat_arb_pairs','ETH/BTC'))
        result['comparison_books'].append(dict(book,split=split,strategy='stat_arb_pairs',symbol='ETH/BTC'))
        result['pair_stop_audit'][split] = audit_pair_stops(window['ETHUSDT'],window['BTCUSDT'])
    result['independent_account_aggregates'] = {}
    for split in ('TRAIN','TEST'):
        rows = [r for r in result['comparison_books'] if r['split']==split]
        # Align account equity by bar; never use max(component drawdown).
        curves = [r['equity_curve'] for r in rows]
        combined = [sum(values) for values in zip(*curves,strict=True)]
        result['independent_account_aggregates'][split] = trade_metrics(
            [t for r in rows for t in r['trades']],70000.0,combined)
    result['stationarity'] = stationarity_windows(store)
    result['legacy'] = audit_legacy(sandbox/'tmp/frozen_fleet_baseline.py',store)
    result['old_report_observed_artifact'] = json.loads((sandbox/'tmp/old_fleet_report.json').read_text(encoding='utf-8'))
    output = sandbox/'phase2-results.json'
    output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    summary = dict(dataset=result['dataset'],cache=result['cache'],
                   risk_exercises=result['risk_exercises'],stationarity=result['stationarity'],
                   legacy_pair_violations=result['legacy']['pair_violation_count'])
    for split in ('TRAIN','TEST'):
        summary[split] = {mode:dict(metrics=r['metrics'],stages=r['stages'],no_signal=r['no_signal'])
                         for mode,r in result['shared_account'][split].items()}
    print(json.dumps(summary,indent=2,allow_nan=False))
    print('RESULT_FILE='+str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',help='Exact-input recorded debate cache JSON')
    args = parser.parse_args()
    # This guard prevents accidental launch in the original workspace.
    sandbox = os.environ.get('ZILLERS_AUDIT_SANDBOX')
    if not sandbox or Path.cwd().resolve()!=Path(sandbox).resolve() or not (Path(sandbox)/'sitecustomize.py').is_file():
        parser.error('Use scripts/run_phase2_research.py; disposable offline research only')
    logging.getLogger().setLevel(logging.WARNING)
    asyncio.run(research(args))


if __name__ == '__main__':
    main()
