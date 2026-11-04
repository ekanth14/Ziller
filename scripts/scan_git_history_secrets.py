"""Run GitLeaks plus configured-value checks without emitting sensitive matches.

No raw detector output is written. Historical candidate findings are retained
only as safe file/object identifiers and counts. History is never changed.
"""
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptoscope.security.report_secrets import configured_secrets, fragments, redact


def main():
    tool = shutil.which('gitleaks')
    if not tool:
        print(json.dumps({'status': 'NOT RUN', 'reason': 'GitLeaks is not installed'}))
        return 2
    command = [tool, 'git', '--redact=100', '--no-banner', '--no-color',
               '--log-opts=--all', '--report-format=json', '--report-path=-', str(ROOT)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    try:
        findings = json.loads(run.stdout) if run.stdout.strip() else []
        if run.returncode not in (0, 1) or not isinstance(findings, list):
            raise ValueError
    except ValueError:
        print(json.dumps({'status': 'FAIL', 'reason': 'Detector did not return a valid redacted report'}))
        return 2
    summary = {
        'head_at_scan': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'tool': subprocess.check_output([tool, 'version'], text=True).strip(),
        'command': 'gitleaks git --redact=100 --no-banner --no-color --log-opts=--all --report-format=json --report-path=- .',
        'detector_exit': run.returncode, 'detector_findings': len(findings),
        'detector_rules': dict(Counter(r.get('RuleID', 'unknown') for r in findings)),
        'detector_locations': sorted({(r.get('File', ''), r.get('Commit', '')) for r in findings}),
    }
    sensitive = configured_secrets(ROOT)
    boundaries = [s.encode() for s in fragments(sensitive)]
    listing = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=ROOT).decode().splitlines()
    objects = {}
    for line in listing:
        oid, _, name = line.partition(' ')
        objects.setdefault(oid, name)
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    candidates = []
    text_blobs, binary_blobs = 0, 0
    try:
        for oid, name in objects.items():
            process.stdin.write((oid + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3:
                raise RuntimeError('Git object read failed')
            body = process.stdout.read(int(header[2]))
            process.stdout.read(1)
            if header[1] != 'blob':
                continue
            if b'\0' in body:
                binary_blobs += 1
                continue
            text_blobs += 1
            if any(value in body for value in boundaries):
                candidates.append({'file': name, 'object': oid})
    finally:
        process.stdin.close()
        process.wait()
    summary.update(text_blobs_scanned=text_blobs, binary_blobs_skipped=binary_blobs,
                   configured_value_candidate_count=len(candidates),
                   configured_value_candidates=candidates[:3],
                   candidate_list_truncated=len(candidates) > 3)
    print(redact(json.dumps(summary), sensitive))
    return int(bool(findings or candidates))


if __name__ == '__main__':
    raise SystemExit(main())
