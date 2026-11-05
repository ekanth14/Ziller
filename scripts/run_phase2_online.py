"""Authorized local Ollama generation, then a separate offline cache replay."""
import json
import subprocess
import sys

from run_isolated_tests import GUARD,ROOT,prepare


def local_model_guard():
    """Separate guard; the normal test/research guard still denies all models."""
    old = "if url.hostname not in ('localhost', '127.0.0.1', '::1') or url.port == 11434:"
    new = "if not (url.hostname == '127.0.0.1' and url.port == 11434 and url.scheme == 'http' and url.path == '/api/generate'):"
    assert GUARD.count(old)==1
    result = GUARD.replace(old,new)
    old_socket = 'if not local or address[1] == 11434:'
    assert result.count(old_socket)==1
    return result.replace(old_socket,'if not local:')


def main():
    destination,environment = prepare()
    source = subprocess.check_output(['git','show','676af22:cryptoscope/research/run_fleet_backtest.py'],cwd=ROOT)
    (destination/'tmp/frozen_fleet_baseline.py').write_bytes(source)
    (destination/'tmp/old_fleet_report.json').write_bytes((ROOT/'work/reports/fleet_backtest_report.json').read_bytes())
    (destination/'sitecustomize.py').write_text(local_model_guard(),encoding='utf-8')
    environment['ZILLERS_LOCAL_MODEL_CACHE'] = '1'
    print('DISPOSABLE_COPY='+str(destination),flush=True)
    command = [sys.executable,'-B','-m','cryptoscope.backtesting.local_model_cache',*sys.argv[1:]]
    with (destination/'online-job-output.txt').open('w',encoding='utf-8') as log:
        generation = subprocess.run(command,cwd=destination,env=environment,stdout=log,stderr=subprocess.STDOUT)
    # Restore the original guard before replay; no model access in backtesting.
    (destination/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    environment.pop('ZILLERS_LOCAL_MODEL_CACHE',None)
    print(json.dumps(dict(generation_exit=generation.returncode)),flush=True)
    if generation.returncode:
        return generation.returncode
    command = [sys.executable,'-B','-m','cryptoscope.research.run_fleet_backtest',
               '--cache',str(destination/'local-debate-cache.json')]
    with (destination/'research-output.txt').open('w',encoding='utf-8') as log:
        result = subprocess.run(command,cwd=destination,env=environment,stdout=log,stderr=subprocess.STDOUT)
    print(json.dumps(dict(replay_exit=result.returncode,results=str(destination/'phase2-results.json'),
                          cache=str(destination/'local-debate-cache.json'))),flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
