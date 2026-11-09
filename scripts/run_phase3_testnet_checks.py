"""Preview or, after separate approval, run bounded Binance Spot Testnet checks.

The executable mode creates only disposable local state. It never starts the
fleet, touches the production governor, or enables LIVE trading. If an order
becomes ambiguous, its state is retained for operator reconciliation.
"""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
import subprocess
import sys
import time

from run_isolated_tests import prepare

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ALLOWED_URL='https://testnet.binance.vision'


def _credentials():
    """Read only the two dedicated values without importing general settings."""
    selected={key:os.environ.get(key,'') for key in
              ('BINANCE_TESTNET_API_KEY','BINANCE_TESTNET_API_SECRET')}
    path=ROOT/'.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1);key=key.strip()
            if key in selected and not selected[key]:selected[key]=value.strip().strip("'\"")
    if not all(selected.values()):raise RuntimeError('Dedicated Testnet settings unavailable')
    return selected


def _guard():
    # The same filesystem audit as isolated pytest, with the single official
    # Testnet endpoint substituted for loopback. DNS is resolved before the
    # socket hook; direct connections to unrelated IPs remain denied.
    from run_isolated_tests import GUARD
    before="import sys, os, pathlib, ipaddress, tempfile, urllib.parse, urllib.request"
    after=before+", socket\n_allowed_ips = {row[4][0] for row in socket.getaddrinfo('testnet.binance.vision', 443, type=socket.SOCK_STREAM)}"
    guard=GUARD.replace(before,after)
    guard=guard.replace("url.hostname not in ('localhost', '127.0.0.1', '::1') or url.port == 11434",
                        "url.scheme != 'https' or url.hostname != 'testnet.binance.vision' or url.port not in (None, 443)")
    guard=guard.replace("if not local or address[1] == 11434:",
                        "if (not local or address[1] == 11434) and (address[0] not in _allowed_ips or address[1] != 443):")
    guard=guard.replace("if args[0] not in ('localhost', '127.0.0.1', '::1', None):",
                        "if args[0] not in ('localhost', '127.0.0.1', '::1', None, 'testnet.binance.vision'):")
    if (guard.count('_allowed_ips')!=2 or "if not local or address[1] == 11434:" in guard
        or "url.hostname not in ('localhost'" in guard):
        raise RuntimeError('Diagnostic network guard construction failed')
    return guard


def _resume_environment(root,selected):
    env=dict(os.environ)
    for key in list(env):
        if any(word in key.upper() for word in ('SECRET','TOKEN','PASSWORD','PASSCODE','API_KEY','OLLAMA',
                   'TELEGRAM','WEBHOOK','DISCORD','TRADING_MODE','ADMIN_EMAIL','INVITE_CODE',
                   'SIGNUP_MODE','GOVERNOR_STATE_DB')):env.pop(key,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONPATH=str(root),
        ZILLERS_AUDIT_SANDBOX=str(root),TEMP=str(root/'tmp'),TMP=str(root/'tmp'),LIVE_TRADING='false',
        SIGNUP_MODE='closed',ACCOUNT_SIZE_USD='1000')
    env.update(selected)
    env.update(ZILLERS_APPROVED_TESTNET_CHECKS='bounded-phase3-v1',
               TRADING_MODE='TESTNET',BINANCE_TESTNET_BASE_URL=ALLOWED_URL,
               HTTP_PROXY='',HTTPS_PROXY='',ALL_PROXY='',NO_PROXY='*')
    return env


def _restart(root,env,log):
    stage=[sys.executable,'-B','-m','cryptoscope.execution.phase3_checks']
    restarted=subprocess.run([*stage,'--stage','restart'],cwd=root,env=env,
        stdout=log,stderr=subprocess.STDOUT,timeout=120)
    result_file=root/'tmp/exchange-check/integration-result.json'
    result=json.loads(result_file.read_text(encoding='utf-8')) if result_file.is_file() else {}
    print(json.dumps(dict(status=result.get('status','missing'),
        bounded_lifecycle=result.get('bounded_lifecycle','NOT_RUN'),
        full_phase3_integration=result.get('full_phase3_integration','NOT_COMPLETE'),
        operator_reconciliation_required=result.get('operator_reconciliation_required',False),
        result_file=str(result_file),restart_exit=restarted.returncode)),flush=True)
    return restarted.returncode


def run_approved(resume_root=None,inspect_only=False,filter_only=False,ledger_only=False):
    selected=_credentials()
    if os.environ.get('BINANCE_TESTNET_BASE_URL',ALLOWED_URL).rstrip('/')!=ALLOWED_URL:
        raise RuntimeError('Only official Binance Spot Testnet is allowed')
    if resume_root is None:root,env=prepare()
    else:
        root=Path(resume_root).resolve()
        if (not root.is_dir() or not root.name.startswith('zillers-phase-audit-')
            or not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not (root/'tmp/exchange-check/restart-required').is_file()
            or not (root/'tmp/exchange-check/integration-result.json').is_file()):
            raise RuntimeError('Only the retained protected diagnostic can be resumed')
        env=_resume_environment(root,selected)
    (root/'sitecustomize.py').write_text(_guard(),encoding='utf-8')
    if resume_root is not None:
        source=ROOT/'cryptoscope/execution/phase3_checks.py'
        target=root/'cryptoscope/execution/phase3_checks.py'
        shutil.copy2(source,target)
    env.update(selected)
    env.update(ZILLERS_APPROVED_TESTNET_CHECKS='bounded-phase3-v1',
               TRADING_MODE='TESTNET',LIVE_TRADING='false',
               BINANCE_TESTNET_BASE_URL=ALLOWED_URL,
               HTTP_PROXY='',HTTPS_PROXY='',ALL_PROXY='',NO_PROXY='*')
    stage=[sys.executable,'-B','-m','cryptoscope.execution.phase3_checks']
    print('DISPOSABLE_COPY='+str(root),flush=True)
    log=(root/'exchange-check-output.txt').open('w',encoding='utf-8')
    if resume_root is not None:
        try:
            if ledger_only:
                checked=subprocess.run([*stage,'--stage','ledger'],cwd=root,env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=30)
                result=json.loads((root/'tmp/exchange-check/integration-result.json').read_text(encoding='utf-8'))
                print(json.dumps(dict(ledger_reconciled=result.get('ledger_reconciled',False),
                    operator_reconciliation_required=result.get('operator_reconciliation_required'),
                    exit=checked.returncode)),flush=True)
                return checked.returncode
            if filter_only:
                checked=subprocess.run([*stage,'--stage','filters'],cwd=root,env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=30)
                result=json.loads((root/'tmp/exchange-check/integration-result.json').read_text(encoding='utf-8'))
                check=next((item for item in result.get('filter_checks',[]) if item['case']=='min_notional'),{})
                print(json.dumps(dict(recheck=check.get('result','NOT_RUN'),code=check.get('code'),
                    bounded_lifecycle=result.get('bounded_lifecycle'),exit=checked.returncode)),flush=True)
                return checked.returncode
            if inspect_only:
                observed=subprocess.run([*stage,'--stage','inspect'],cwd=root,env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=30)
                path=root/'tmp/exchange-check/inspection.json'
                if observed.returncode==0 and path.is_file():print(path.read_text(encoding='utf-8'),flush=True)
                else:print('Read-only inspection failed; retained state unchanged',flush=True)
                return observed.returncode
            return _restart(root,env,log)
        finally:log.close()
    child=subprocess.Popen([*stage,'--stage','entry'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    marker=root/'tmp/exchange-check/restart-required'
    deadline=time.monotonic()+120
    try:
        while not marker.is_file() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.2)
        if not marker.is_file():
            raise RuntimeError('Diagnostic did not confirm resting protection before deadline')
        # Terminate only this child after its durable protected marker exists.
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        return _restart(root,env,log)
    except Exception:
        print('Diagnostic stopped; inspect own retained references and exchange exposure before any retry',flush=True)
        return 1
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved-checks',action='store_true')
    parser.add_argument('--resume-disposable',type=Path)
    parser.add_argument('--inspect-disposable',type=Path)
    parser.add_argument('--recheck-filter-disposable',type=Path)
    parser.add_argument('--reconcile-ledger-disposable',type=Path)
    args=parser.parse_args()
    from cryptoscope.execution.phase3_checks import PLAN
    selected=[value for value in (args.resume_disposable,args.inspect_disposable,
        args.recheck_filter_disposable,args.reconcile_ledger_disposable) if value is not None]
    if len(selected)>1:parser.error('Choose one retained-state action')
    if not args.execute_approved_checks and not selected:
        print(json.dumps(dict(mode='PREVIEW_ONLY',plan=PLAN),indent=2))
        return 0
    if os.environ.get('ZILLERS_APPROVED_TESTNET_CHECKS')!='bounded-phase3-v1':
        raise SystemExit('Separate order authorization and diagnostic flag required')
    return run_approved(selected[0] if selected else None,
                        inspect_only=args.inspect_disposable is not None,
                        filter_only=args.recheck_filter_disposable is not None,
                        ledger_only=args.reconcile_ledger_disposable is not None)


if __name__=='__main__':raise SystemExit(main())
