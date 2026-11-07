"""Automatic local backups and restore checks; never overwrite or delete old copies."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from cryptoscope.ops.databases import backup_and_verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--interval',type=int,default=0,help='Seconds between backups; 0 takes one snapshot')
    args=parser.parse_args()
    if args.interval and args.interval<60:parser.error('Interval must be at least 60 seconds')
    while True:
        name=datetime.now(timezone.utc).strftime('phase3-%Y%m%dT%H%M%S-%fZ')
        target=args.root/'work/backups'/name
        try:
            result=backup_and_verify(args.root,target)
            print(json.dumps(dict(destination=str(target),databases=len(result['databases']),passed=result['passed'])),flush=True)
        except Exception as error:
            # Retain incomplete snapshots for diagnosis; do not disclose rows or
            # stop a periodic backup schedule after one transient failure.
            print(json.dumps(dict(destination=str(target),passed=False,error_type=type(error).__name__)),flush=True)
            if not args.interval:return 1
        if not args.interval:break
        time.sleep(args.interval)


if __name__=='__main__':raise SystemExit(main())
