"""Versioned local research committee. No hidden model template or sizing power."""
import hashlib
import json
import math
import socket
import time
import urllib.error
import urllib.request

PROTOCOL = 'phase2-scored-committee-v1'
SCHEMA = {'type':'object','properties':{
    key:{'type':'integer','minimum':0,'maximum':1 if key=='vote' else 10}
    for key in ('bull','bear','risk','vote')},
    'required':['bull','bear','risk','vote'],'additionalProperties':False}


class CompactDebateEngine:
    def deliberate_combined(self, *, symbol,direction,entry,stop,target,indicators,
                           model,timeout_sec):
        started = time.perf_counter()
        prompt = (
            'Historical research committee. Assess separately: bull support, bear opposition, '
            'risk moderator conviction, each 0-10. vote=1 only if the risk moderator approves '
            'the proposed direction; otherwise 0. No future information or assumed news. '
            'Return only the four integer fields in JSON. Proposal: '+
            json.dumps(dict(symbol=symbol,direction=direction,entry=entry,stop=stop,target=target,
                            strategy=indicators.get('strategy')),sort_keys=True,allow_nan=False)+'\nJSON:')
        settings = dict(temperature=0,num_predict=40,num_ctx=512,num_thread=4,seed=17)
        payload = dict(model=model,prompt=prompt,raw=True,think=False,stream=False,
                       format=SCHEMA,options=settings,keep_alive='15m')
        provenance = dict(protocol=PROTOCOL,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                          generation_options=settings)
        json_valid = None
        timing = {}
        try:
            request = urllib.request.Request('http://127.0.0.1:11434/api/generate',
                data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=timeout_sec) as response:
                body = json.load(response)
            elapsed = (time.perf_counter()-started)*1000
            if elapsed > timeout_sec*1000:
                raise TimeoutError()
            if not isinstance(body,dict):
                raise ValueError('incomplete_generation')
            result = json.loads(body.get('response',''))
            json_valid = True
            timing = {k:body.get(k) for k in ('load_duration','prompt_eval_duration',
                    'eval_duration','prompt_eval_count','eval_count')}
            if body.get('done') is not True or body.get('done_reason') != 'stop':
                raise ValueError('incomplete_generation')
            if not isinstance(result,dict) or set(result)!=set(SCHEMA['required']):
                raise ValueError('invalid_schema')
            if any(type(result[k]) is not int or not 0 <= result[k] <= (1 if k=='vote' else 10) for k in result):
                raise ValueError('invalid_schema')
            approved = result['vote']==1 and result['risk']>=6
            return dict(model=model,verdict='APPROVE' if approved else 'REJECT',
                action=direction if approved else 'STAND_ASIDE',conviction_score=result['risk'],
                latency_ms=elapsed,fallback_used=False,committee_scores=result,
                output_json_valid=True,**provenance,timing=timing)
        except (TimeoutError,socket.timeout):
            failure='timeout'
        except urllib.error.HTTPError as error:
            failure='http_'+str(error.code)
        except urllib.error.URLError as error:
            failure='timeout' if isinstance(error.reason,(TimeoutError,socket.timeout)) else 'transport'
        except json.JSONDecodeError:
            json_valid=False
            failure='invalid_json'
        except ValueError:
            failure='invalid_or_incomplete_output'
        except OSError:
            failure='transport'
        return dict(model=model,verdict='REJECT',action='STAND_ASIDE',conviction_score=0,
                    fallback_used=True,latency_ms=(time.perf_counter()-started)*1000,
                    failure_category=failure,output_json_valid=json_valid,timing=timing,**provenance)
