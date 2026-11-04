"""Report only counts and safe file identifiers; optionally redact reports in place."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptoscope.security.report_secrets import configured_secrets, redact_document, report_files, scan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--redact', action='store_true')
    args = parser.parse_args()
    changed = 0
    if args.redact:
        secrets = configured_secrets(ROOT)
        for path in report_files(ROOT):
            if not path.resolve().is_relative_to(ROOT.resolve()):
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            try:
                safe = redact_document(text, secrets, path.suffix)
            except ValueError:
                continue  # The scan below reports unrelated invalid JSON as a failure.
            if safe != text:
                path.write_text(safe, encoding='utf-8')
                changed += 1
    result = scan(ROOT)
    print(json.dumps({'files_redacted': changed, **result}))
    return int(bool(result['findings']))


if __name__ == '__main__':
    raise SystemExit(main())
