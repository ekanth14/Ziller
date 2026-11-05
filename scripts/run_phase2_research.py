"""Retained disposable Phase 2 offline research, using the reviewed audit guard."""
import json
from pathlib import Path
import subprocess
import sys

from run_isolated_tests import ROOT,prepare


def main():
    destination,environment = prepare()
    # Read committed local baseline; never checkout or run its CLI/data loader.
    source = subprocess.check_output(['git','show','676af22:cryptoscope/research/run_fleet_backtest.py'],cwd=ROOT)
    (destination/'tmp/frozen_fleet_baseline.py').write_bytes(source)
    old = ROOT/'work/reports/fleet_backtest_report.json'
    (destination/'tmp/old_fleet_report.json').write_bytes(old.read_bytes())
    command = [sys.executable,'-B','-m','cryptoscope.research.run_fleet_backtest',*sys.argv[1:]]
    print('DISPOSABLE_COPY='+str(destination),flush=True)
    result = subprocess.run(command,cwd=destination,env=environment,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True,encoding='utf-8')
    (destination/'research-output.txt').write_text(result.stdout,encoding='utf-8')
    # Do not print large raw artifacts. Inspect retained evidence through the
    # workspace report scanner before bringing any values into reports.
    print(json.dumps(dict(exit_code=result.returncode,output=str(destination/'research-output.txt'),
                          results=str(destination/'phase2-results.json'))))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
