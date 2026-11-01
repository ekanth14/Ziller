"""Explicit model download and forecast artifact commands."""
import argparse
import json
from pathlib import Path
import sys
import uuid
from cryptoscope.agents.schemas import Snapshot
from cryptoscope.forecasting import forecast
from cryptoscope.research.settings import ROOT


def download():
    from huggingface_hub import HfApi, snapshot_download
    root=ROOT/'data/models/kronos'
    root.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8')) if (root/'manifest.json').exists() else {}
    for name,repository in [('tokenizer','NeoQuasar/Kronos-Tokenizer-base'),('model','NeoQuasar/Kronos-small')]:
        revision=manifest.get(name,{}).get('revision') or HfApi().model_info(repository,token=False).sha
        snapshot_download(repository, revision=revision, local_dir=root/name,
                          allow_patterns=['config.json','model.safetensors'],token=False)
        manifest[name]={'repository':repository,'revision':revision}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'status':'downloaded','models':manifest}


def main():
    parser=argparse.ArgumentParser(description='Optional local Kronos forecasts; not trade decisions')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('download',help='Explicitly download and pin the official model weights')
    run=commands.add_parser('run')
    run.add_argument('--snapshot',type=Path,required=True)
    run.add_argument('--steps',type=int,default=12)
    run.add_argument('--samples',type=int,default=3)
    run.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    try:
        if args.command=='download':
            result=download()
        else:
            snapshot=Snapshot.parse(json.loads(args.snapshot.read_text(encoding='utf-8')))
            result=forecast(snapshot,args.steps,args.samples,args.seed)
            run_id=uuid.uuid4().hex
            output=ROOT/'reports/forecasts'/run_id
            output.mkdir(parents=True)
            result={**result,'run_id':run_id}
            (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0
    except Exception as error:
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1


raise SystemExit(main())
