"""Run a real 30-minute operations soak on a disposable dashboard, never production."""
import argparse
import csv
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

from run_isolated_tests import prepare

WRAPPER = '''import signal,threading,time
from pathlib import Path
def watch():
    while not Path('shutdown-requested').exists():time.sleep(0.2)
    signal.raise_signal(signal.SIGINT)
threading.Thread(target=watch,daemon=True).start()
from cryptoscope.dashboard.__main__ import main
main()
'''


def throughput(port, persistent, count=100):
    opened=success=0;versions=set();start=time.perf_counter();conn=None
    for _ in range(count):
        if conn is None:
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5);opened+=1
        try:
            conn.request('GET','/health',headers={'Connection':'keep-alive' if persistent else 'close'})
            response=conn.getresponse();response.read();versions.add(response.version)
            success+=response.status==200
            if not persistent or response.will_close:
                conn.close();conn=None
        except (OSError,http.client.HTTPException):
            conn.close();conn=None
    if conn:conn.close()
    duration=time.perf_counter()-start
    return dict(mode='keep_alive' if persistent else 'close',requests=count,successful=success,
                tcp_connections_opened=opened,http_versions=sorted(versions),seconds=duration,
                successful_requests_per_second=success/duration)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=int,default=1800)
    parser.add_argument('--clients',type=int,default=50)
    parser.add_argument('--interval',type=int,default=30)
    args=parser.parse_args()
    if args.duration<5 or not 1<=args.clients<=100 or args.interval<1:parser.error('Invalid limits')
    root,environment=prepare()
    (root/'soak_server.py').write_text(WRAPPER,encoding='utf-8')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    log=(root/'server-output.txt').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'-B','soak_server.py','--port',str(port)],
        cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT)
    def get(path):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=5) as response:return json.load(response)
    print('DISPOSABLE_COPY='+str(root),flush=True)
    for _ in range(100):
        if server.poll() is not None:raise RuntimeError('Isolated server failed to start; inspect retained log')
        try:
            get('/health');break
        except OSError:time.sleep(.2)
    else:raise RuntimeError('Isolated startup timed out')
    before=[throughput(port,False),throughput(port,True)]
    stop=threading.Event();lock=threading.Lock();errors={}
    counters=dict(active_sse=0,sse_connects=0,sse_frames=0,sse_failures=0,api_ok=0,api_failed=0)
    def increment(key,n=1):
        with lock:counters[key]+=n
    def failure(kind,error):
        increment(kind+'_failures' if kind=='sse' else 'api_failed')
        key=kind+':'+type(error).__name__
        with lock:errors[key]=errors.get(key,0)+1
    def sse_worker():
        while not stop.is_set():
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5);active=False
            try:
                conn.request('GET','/api/market/stream');response=conn.getresponse()
                if response.status!=200:raise OSError('SSE rejected')
                increment('active_sse');increment('sse_connects');active=True
                while not stop.is_set():
                    line=response.readline()
                    if not line:break
                    if line.startswith(b'data: '):increment('sse_frames')
            except (OSError,http.client.HTTPException) as error:failure('sse',error)
            finally:
                if active:increment('active_sse',-1)
                conn.close()
            stop.wait(.05)
    def api_worker():
        conn=None;index=0
        while not stop.is_set():
            started=time.monotonic()
            try:
                if conn is None:conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                conn.request('GET',('/health','/api/market/status','/api/laya/status')[index%3])
                response=conn.getresponse();response.read();index+=1
                increment('api_ok' if response.status==200 else 'api_failed')
                if response.will_close:conn.close();conn=None
            except (OSError,http.client.HTTPException) as error:
                failure('api',error)
                if conn:conn.close();conn=None
            stop.wait(max(0,.2-(time.monotonic()-started)))
        if conn:conn.close()
    workers=[]
    for _ in range(args.clients):
        t=threading.Thread(target=sse_worker,daemon=True);t.start();workers.append(t);time.sleep(.03)
    traffic=threading.Thread(target=api_worker,daemon=True);traffic.start()
    started=time.monotonic();samples=[]
    columns=['utc','elapsed_seconds','rss_mb','threads','sockets',*counters]
    with (root/'soak-metrics.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        while True:
            elapsed=time.monotonic()-started
            try:metrics=get('/api/market/status')['server']
            except (OSError,http.client.HTTPException):metrics=dict(rss_mb=None,threads=None,sockets=None)
            with lock:counts=dict(counters)
            row=dict(utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(elapsed,3),**{k:metrics[k] for k in ['rss_mb','threads','sockets']},**counts)
            writer.writerow(row);file.flush();samples.append(row)
            print(json.dumps(row),flush=True)
            if elapsed>=args.duration:break
            time.sleep(min(args.interval,args.duration-elapsed))
    # Request internal signal shutdown while all clients/API traffic remain active.
    with lock:load_counters=dict(counters);load_errors=dict(errors)
    (root/'shutdown-requested').write_text('stop isolated soak only',encoding='utf-8')
    shutdown_start=time.monotonic()
    try:server.wait(timeout=20);graceful=server.returncode==0
    except subprocess.TimeoutExpired:
        graceful=False;server.terminate();server.wait(timeout=10)
    shutdown_seconds=time.monotonic()-shutdown_start
    stop.set()
    for t in workers+[traffic]:t.join(timeout=6)
    log.close()
    def slope(rows):
        points=[(r['elapsed_seconds']/60,r['rss_mb']) for r in rows if r['rss_mb'] is not None]
        if len(points)<2:return None
        x=statistics.mean(a for a,b in points);y=statistics.mean(b for a,b in points)
        denominator=sum((a-x)**2 for a,b in points)
        return sum((a-x)*(b-y) for a,b in points)/denominator if denominator else None
    tail=samples[len(samples)//2:]
    tail_slope=slope(tail)
    plateau=(tail_slope is not None and all(r['rss_mb'] is not None for r in tail) and abs(tail_slope)<=0.1 and
             max(r['rss_mb'] for r in tail)-min(r['rss_mb'] for r in tail)<=10)
    result=dict(duration_seconds=samples[-1]['elapsed_seconds'],target_clients=args.clients,
        metrics='real server process metrics; sockets are owned TCP rows, not client count',
        sample_count=len(samples),sampling_interval_seconds=args.interval,
        slope_mb_per_minute=slope(samples),tail_slope_mb_per_minute=tail_slope,
        plateau=plateau,plateau_rule='second-half absolute slope <=0.1 MB/min and range <=10 MB',
        throughput=before,graceful_shutdown=graceful,shutdown_seconds=shutdown_seconds,
        server_exit=server.returncode,counters=load_counters,error_types=load_errors,
        shutdown_counters=dict(counters),minimum_sampled_active_sse=min(r['active_sse'] for r in samples),
        maximum_sampling_gap_seconds=max(b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(samples,samples[1:])),
        status='PASS' if args.duration>=1800 and args.clients>=50 and plateau and graceful and
            all(r['rss_mb'] is not None and r['sockets'] is not None for r in samples) and
            load_counters['api_failed']==0 and load_counters['sse_failures']==0 and
            max(b['elapsed_seconds']-a['elapsed_seconds'] for a,b in zip(samples,samples[1:]))<=args.interval+5 else 'REVIEW')
    (root/'soak-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
