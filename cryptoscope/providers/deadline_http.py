"""Bound local model I/O in a disposable process; socket timeouts alone are insufficient."""
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# CPU-only 12B models need 60-120 s per answer; the worker is still killed at the deadline.
MAX_DEADLINE_SEC=300.0


def _local_url(url):
    parsed=urllib.parse.urlsplit(url)
    if (parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'}
            or parsed.username or parsed.password or parsed.query or parsed.path!='/api/generate'):
        raise ValueError('Model transport requires a local generation endpoint')


def post_json_deadline(url,payload,timeout_sec):
    _local_url(url)
    if not math.isfinite(timeout_sec) or not 0<timeout_sec<=MAX_DEADLINE_SEC:
        raise ValueError(f'Model deadline must be positive and at most {MAX_DEADLINE_SEC:.0f} seconds')
    deadline=time.monotonic()+timeout_sec
    allowed={'SYSTEMROOT','WINDIR','PATH','PYTHONPATH','TEMP','TMP','ZILLERS_AUDIT_SANDBOX',
             'PYTHONDONTWRITEBYTECODE','PYTHONIOENCODING'}
    env={k:v for k,v in os.environ.items() if k.upper() in allowed}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    process=subprocess.Popen([sys.executable,'-B','-m',__name__,'--worker'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
    try:
        remaining=deadline-time.monotonic()-.15
        if remaining<=0:raise subprocess.TimeoutExpired('model-worker',timeout_sec)
        output,_=process.communicate(json.dumps(dict(url=url,payload=payload,timeout=remaining)).encode(),timeout=remaining)
        if time.monotonic()>=deadline:raise TimeoutError('Model deadline exceeded')
        if process.returncode!=0:raise OSError('Model worker failed')
        result=json.loads(output)
        if result.get('kind')=='timeout':raise TimeoutError('Model deadline exceeded')
        if result.get('kind')=='http':raise urllib.error.HTTPError(url,result['status'],'Model endpoint rejected request',None,None)
        if result.get('kind')!='success':raise OSError('Model transport failed')
        return result['body']
    except subprocess.TimeoutExpired:
        raise TimeoutError('Model deadline exceeded') from None
    finally:
        if process.poll() is None:
            process.kill()
            try:process.communicate(timeout=.1)
            except subprocess.TimeoutExpired:
                # Only our own worker is reaped. Never wait indefinitely on the
                # trading/event loop, and never retain a running HTTP worker.
                threading.Thread(target=process.communicate,daemon=True).start()


def _worker():
    request=json.load(sys.stdin);_local_url(request['url'])
    try:
        req=urllib.request.Request(request['url'],data=json.dumps(request['payload']).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=request['timeout']) as response:
            body=response.read(1024*1024+1)
            if len(body)>1024*1024:raise ValueError('Model response exceeded limit')
        result=dict(kind='success',body=json.loads(body))
    except urllib.error.HTTPError as error:result=dict(kind='http',status=error.code)
    except (TimeoutError,):result=dict(kind='timeout')
    except Exception:result=dict(kind='transport')
    sys.stdout.write(json.dumps(result))


if __name__=='__main__':
    if sys.argv[1:]!=['--worker']:raise SystemExit('Internal model worker only')
    _worker()
