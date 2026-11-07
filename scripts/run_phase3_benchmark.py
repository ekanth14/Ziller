"""Launch the approved installed-model benchmark with local generation only."""
import json
import subprocess
import sys
from run_isolated_tests import prepare
from run_phase2_online import local_model_guard


def main():
    root,env=prepare()
    (root/'sitecustomize.py').write_text(local_model_guard(),encoding='utf-8')
    print('DISPOSABLE_COPY='+str(root),flush=True)
    with (root/'benchmark-output.txt').open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,'-B','-m','cryptoscope.ops.debate_benchmark'],
                              cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    print(json.dumps(dict(exit_code=result.returncode,results=str(root/'benchmark-result.json'))),flush=True)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
