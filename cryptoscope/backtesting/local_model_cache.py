"""Explicitly authorized local-model cache job; no exchange or order imports.

Runs only in the retained disposable research environment. Decisions are keyed
to historical inputs. Failure attempts are recorded separately from model votes.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import logging
import math
import os
from pathlib import Path
import time
import urllib.request

from cryptoscope.agents.consensus import DeliberationConsensusEngine
from cryptoscope.backtesting.debate_cache import debate_key
from cryptoscope.backtesting.fleet_replay import FROZEN_PARAMETERS,load_archive,replay
from cryptoscope.security.halt_state import GovernorState


def normalize_vote(raw,request,model,budget):
    """Only successful, direction-consistent model votes become cache hits."""
    score,latency = raw.get('conviction_score'),raw.get('latency_ms')
    valid = (not raw.get('fallback_used',True) and raw.get('model') == model
        and raw.get('verdict') in {'APPROVE','REJECT'}
        and isinstance(score,(int,float)) and not isinstance(score,bool)
        and math.isfinite(score) and 0 <= score <= 10
        and isinstance(latency,(int,float)) and not isinstance(latency,bool)
        and math.isfinite(latency) and 0 <= latency <= budget*1000)
    if not valid:
        return None
    verdict = raw['verdict']
    if raw.get('action') != request['direction'] or score < 6:
        verdict = 'REJECT'
    # Do not persist free-form model text as trusted control information.
    return dict(source='recorded_model',model=model,verdict=verdict,
                conviction_score=score,latency_ms=latency,fallback_used=False,
                recorded_at=datetime.now(timezone.utc).isoformat(),
                action=request['direction'] if verdict=='APPROVE' else 'STAND_ASIDE')


async def discover(root):
    store = load_archive(root/'work/runtime/crypto_candles.db')
    path = root/'tmp/cache-discovery-governor.db'
    os.environ['GOVERNOR_STATE_DB'] = str(path)
    GovernorState(path).resume_local_admin(admin_reauthenticated=True,actor='disposable-research-admin')
    requests = {}
    for lo,hi in ((0,1512),(1512,2160)):
        result = await replay({s:bars[lo:hi] for s,bars in store.items()})
        requests.update(result['debate_requests'])
    return requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='gemma4-quant:12b',choices=('gemma4-quant:12b','gemma4:12b'))
    parser.add_argument('--max-requests',type=int,default=100)
    args = parser.parse_args()
    value = os.environ.get('ZILLERS_AUDIT_SANDBOX')
    if not value or Path.cwd().resolve()!=Path(value).resolve() or os.environ.get('ZILLERS_LOCAL_MODEL_CACHE')!='1':
        parser.error('Use scripts/run_phase2_online.py with explicit local-model authorization')
    root = Path(value)
    # The delegate uses environment configuration. Fix it inside this disposable
    # process; production environment/configuration is never loaded or edited.
    os.environ['OLLAMA_HOST'] = 'http://127.0.0.1:11434'
    os.environ['OLLAMA_DEBATE_MODEL'] = args.model
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    logging.disable(logging.CRITICAL)  # Never persist delegate exception strings.
    requests = asyncio.run(discover(root))
    cache = dict(schema=1,model=args.model,parameters=FROZEN_PARAMETERS,
                 request_count=len(requests),records={},attempts=[],status='running')
    output = root/'local-debate-cache.json'
    progress = root/'local-debate-progress.jsonl'
    engine = DeliberationConsensusEngine()
    budget = 35.0
    failures = 0
    os.environ['DEBATE_TIMEOUT_SEC'] = str(budget)
    print(json.dumps(dict(status='starting',requests=len(requests),model=args.model)),flush=True)
    for index,(key,request) in enumerate(requests.items(),1):
        if index > args.max_requests:
            cache['status'] = 'request_limit_reached'
            break
        assert debate_key(**request) == key
        started = time.perf_counter()
        raw = engine.deliberate_combined(**request,model=args.model,timeout_sec=budget-0.5)
        elapsed = time.perf_counter()-started
        vote = normalize_vote(raw,request,args.model,budget) if elapsed <= budget else None
        if vote is not None:
            cache['records'][key] = vote
            failures = 0
        else:
            failures += 1
        attempt = dict(index=index,input_key=key,elapsed_seconds=round(elapsed,3),
                       status='recorded_model' if vote else 'failed_closed',
                       verdict=vote['verdict'] if vote else 'REJECT')
        cache['attempts'].append(attempt)
        # Checkpoint each completed request. No retries or timeout extension.
        output.write_text(json.dumps(cache,indent=2,allow_nan=False),encoding='utf-8')
        with progress.open('a',encoding='utf-8') as log:
            log.write(json.dumps(attempt)+'\n')
        print(json.dumps(dict(completed=index,total=len(requests),
                              valid=len(cache['records']),failures=failures)),flush=True)
        if failures >= 3:
            cache['status'] = 'stopped_after_three_consecutive_failures'
            break
    else:
        cache['status'] = 'completed'
    output.write_text(json.dumps(cache,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(status=cache['status'],valid=len(cache['records']),
                          attempted=len(cache['attempts']),cache=str(output))),flush=True)


if __name__ == '__main__':
    main()
