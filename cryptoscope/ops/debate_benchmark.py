"""Two real runs on identical historical scenarios, with no cached model responses."""
import asyncio
import csv
import json
import math
import os
from pathlib import Path
import statistics
import time

from cryptoscope.backtesting.compact_debate import CompactDebateEngine,PROTOCOL
from cryptoscope.backtesting.local_model_cache import discover


def quantile(values,p):
    ordered=sorted(values);index=(len(ordered)-1)*p;lo=int(index);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)


def main():
    root=Path(os.environ['ZILLERS_AUDIT_SANDBOX'])
    all_requests=list(asyncio.run(discover(root)).items())
    selected=[all_requests[round(i*(len(all_requests)-1)/29)] for i in range(30)]
    engine=CompactDebateEngine();rows=[];summaries=[]
    columns=['run','scenario','input_id','seconds','json_valid','schema_valid','timeout','failure_category','tokens','tokens_per_second']
    with (root/'benchmark.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        for run in (1,2):
            samples=[]
            for index,(key,request) in enumerate(selected,1):
                started=time.perf_counter()
                output=engine.deliberate_combined(**request,model='gemma4-quant:12b',timeout_sec=34.5)
                seconds=time.perf_counter()-started
                timings=output.get('timing',{});tokens=timings.get('eval_count');ns=timings.get('eval_duration')
                row=dict(run=run,scenario=index,input_id=key,seconds=seconds,
                    json_valid=output.get('output_json_valid') is True,
                    schema_valid=not output['fallback_used'] and seconds<=35,
                    timeout=output.get('failure_category')=='timeout' or seconds>35,
                    failure_category=output.get('failure_category'),tokens=tokens,
                    tokens_per_second=tokens/(ns/1e9) if tokens is not None and ns and ns>0 else None)
                writer.writerow(row);file.flush();rows.append(row);samples.append(row)
                print(json.dumps({k:row[k] for k in ('run','scenario','seconds','json_valid','timeout')}),flush=True)
            summary=dict(run=run,scenarios=len(samples),p50_seconds=quantile([r['seconds'] for r in samples],.5),
                p95_seconds=quantile([r['seconds'] for r in samples],.95),
                valid_json_rate=sum(r['json_valid'] for r in samples)/len(samples),
                valid_schema_rate=sum(r['schema_valid'] for r in samples)/len(samples),
                timeout_rate=sum(r['timeout'] for r in samples)/len(samples),
                tokens_per_second=statistics.mean(r['tokens_per_second'] for r in samples if r['tokens_per_second'] is not None)
                    if any(r['tokens_per_second'] is not None for r in samples) else None)
            summaries.append(summary)
            (root/'benchmark-result.json').write_text(json.dumps(dict(status='running',model='gemma4-quant:12b',protocol=PROTOCOL,runs=summaries),indent=2),encoding='utf-8')
    result=dict(status='completed',model='gemma4-quant:12b',requested_tag='gemma4:12b',
        substitution_explicitly_approved=True,protocol=PROTOCOL,runs=summaries,
        difference={k:summaries[1][k]-summaries[0][k] for k in ('p50_seconds','p95_seconds','valid_json_rate','timeout_rate')},
        note='Scored committee protocol used in Phase 2; not a claim about the longer production consensus prompt. Host also runs isolated load testing.')
    (root/'benchmark-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
