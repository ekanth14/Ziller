"""Stub-based cache validation and guard tests; never call a running model."""
import ast
import ipaddress
import os
from pathlib import Path
import runpy
import urllib.parse

import pytest

from cryptoscope.backtesting.local_model_cache import normalize_vote
from cryptoscope.backtesting.debate_cache import RecordedDebateEngine,debate_key


def vote():
    return dict(model='fixture-not-a-model-run',verdict='APPROVE',action='BUY',
                conviction_score=8,latency_ms=100,fallback_used=False,
                reason='Untrusted free-form text must not be persisted')


def test_normalized_vote_only_records_actual_valid_consistent_model_output():
    result = normalize_vote(vote(),{'direction':'BUY'},'fixture-not-a-model-run',35)
    assert result['source']=='recorded_model'
    assert result['verdict']=='APPROVE'
    assert 'reason' not in result
    assert 'recorded_at' in result


@pytest.mark.parametrize('overrides',[{'fallback_used':True},{'model':'other'},
    {'conviction_score':True},{'conviction_score':float('nan')},{'conviction_score':11},
    {'latency_ms':35001},{'latency_ms':True},{'verdict':'invalid'}])
def test_invalid_or_timed_out_model_output_never_becomes_a_cached_vote(overrides):
    raw=vote();raw.update(overrides)
    assert normalize_vote(raw,{'direction':'BUY'},'fixture-not-a-model-run',35) is None


@pytest.mark.parametrize('overrides',[{'action':'SELL'},{'action':'STAND_ASIDE'},{'conviction_score':5}])
def test_direction_mismatch_and_low_confidence_remain_rejections(overrides):
    raw=vote();raw.update(overrides)
    assert normalize_vote(raw,{'direction':'BUY'},'fixture-not-a-model-run',35)['verdict']=='REJECT'


def test_replay_rejects_cached_opposite_direction():
    request=dict(symbol='BTCUSDT',direction='BUY',entry=100,stop=98,target=104,indicators={})
    record=vote();record.update(source='recorded_model',action='SELL')
    engine=RecordedDebateEngine({debate_key(**request):record})
    assert engine.deliberate_combined(**request,timeout_sec=35)['verdict']=='REJECT'
    assert engine.counts=={'invalid_cache':1}


def audit_function(source):
    function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='_audit')
    namespace={'ipaddress':ipaddress,'urllib':urllib,'os':os,'_inside':lambda p:False}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'audit-test','exec'),namespace)
    return namespace['_audit']




def test_cache_job_checkpoints_and_stops_after_three_failures(tmp_path,monkeypatch):
    import argparse
    import logging
    import cryptoscope.backtesting.local_model_cache as module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ZILLERS_AUDIT_SANDBOX',str(tmp_path))
    monkeypatch.setenv('ZILLERS_LOCAL_MODEL_CACHE','1')
    for name in ('OLLAMA_HOST','OLLAMA_DEBATE_MODEL','DEBATE_TIMEOUT_SEC'):
        monkeypatch.setenv(name,'fixture')
    monkeypatch.setattr(logging,'disable',lambda _:None)
    monkeypatch.setattr(module.urllib.request,'install_opener',lambda _:None)
    monkeypatch.setattr(argparse.ArgumentParser,'parse_args',lambda _:argparse.Namespace(model='gemma4-quant:12b',max_requests=100))
    requests={}
    for entry in (100,101,102,103):
        request=dict(symbol='BTCUSDT',direction='BUY',entry=entry,stop=98,target=110,indicators={})
        requests[debate_key(**request)]=request
    async def discover(_):return requests
    monkeypatch.setattr(module,'discover',discover)
    class Unavailable:
        def deliberate_combined(self,**kwargs):return {'fallback_used':True}
    monkeypatch.setattr(module,'DeliberationConsensusEngine',Unavailable)
    module.main()
    import json
    cache=json.loads((tmp_path/'local-debate-cache.json').read_text(encoding='utf-8'))
    assert cache['status']=='stopped_after_three_consecutive_failures'
    assert len(cache['attempts'])==3
    assert cache['records']=={}
