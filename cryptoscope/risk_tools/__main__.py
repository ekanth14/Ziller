"""Python entry point for optional, offline CloddsBot risk utilities."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run(input_data=None):
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 24+ is required for native TypeScript risk modules')
    version = subprocess.run([node, '--version'], text=True, capture_output=True, check=True, timeout=10).stdout.strip()
    if int(version.lstrip('v').split('.')[0]) < 24:
        raise RuntimeError('Node.js 24+ is required; no global npm installation is necessary')
    command = [node, str(ROOT / 'integrations/clodds-risk/cli.mjs'), '--demo' if input_data is None else '--stdin']
    result = subprocess.run(command, input=None if input_data is None else json.dumps(input_data, allow_nan=False),
                            text=True, capture_output=True, timeout=30, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Risk diagnostics failed')
    report = json.loads(result.stdout)
    return report


def main():
    parser = argparse.ArgumentParser(description='Offline Clodds risk diagnostics; advisory only')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo', action='store_true', help='Synthetic offline installation verification')
    source.add_argument('--input', type=Path, help='Risk observations and long positions as JSON')
    args = parser.parse_args()
    try:
        report = run(json.loads(args.input.read_text(encoding='utf-8')) if args.input else None)
        if args.demo:
            if report['volatility']['regime'] != 'extreme' or report['risk']['historicalVaR'] != 50:
                raise RuntimeError('Synthetic installation verification failed')
            path = ROOT / 'work/clodds-risk/verification.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
