"""Scan report text without returning sensitive matches or their offsets."""
from pathlib import Path
import json
import re

SECRET_NAME = re.compile(r'KEY|SECRET|TOKEN|PASSWORD|PASSCODE|INVITE_CODE', re.I)
DESCRIPTION = re.compile(
    r'(?<![A-Za-z0-9])(?:keys?|secrets?|credentials?|tokens?|passwords?|passcodes?)'
    r'(?![A-Za-z0-9]).{0,100}(?<![A-Za-z0-9])'
    r'(?:\d+[ -]?(?:char(?:acter)?s?|bytes?)|starts? with|ends? with|begins? with|'
    r'prefix|suffix|positions?|alphanumeric|length|format|characters?|chars?|bytes?|'
    r'at index|first[ _]\d+|last[ _]\d+)(?![A-Za-z0-9])', re.I)
MASKED_LITERAL = re.compile(r'[A-Za-z0-9@_$-]{4,}\.{3}[A-Za-z0-9@_$-]{4,}')
TEXT_SUFFIXES = {'.md', '.json', '.csv', '.txt', '.html', '.log', '.jsonl'}


def configured_secrets(root):
    values = set()
    # Read the legacy file only for detection until its owner approves migration.
    for name in ('.env', 'credentials.env'):
        path = Path(root) / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip().strip('"\'')
            if SECRET_NAME.search(key) and len(value) >= 4:
                values.add(value)
    return values


def fragments(secrets):
    # Matching the shortest forbidden boundary also detects longer boundaries.
    return {part for secret in secrets for part in (secret, secret[:4], secret[-4:])
            if len(part) >= 4}


def violations(text, secrets):
    result = set()
    if any(value in text for value in fragments(secrets)):
        result.add('configured-sensitive-value')
    if any(DESCRIPTION.search(line) for line in text.splitlines()):
        result.add('sensitive-description')
    if MASKED_LITERAL.search(text):
        result.add('masked-sensitive-literal')
    return sorted(result)


def redact(text, secrets):
    for value in sorted(fragments(secrets), key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    text = MASKED_LITERAL.sub('[REDACTED]', text)
    return ''.join('[REDACTED SECURITY NOTE]\n' if DESCRIPTION.search(line) else line
                   for line in text.splitlines(keepends=True))


def redact_document(text, secrets, suffix):
    """Preserve JSON structure. Withheld numeric values become explicit nulls.

    Repair only numeric tokens damaged by the earlier literal redactor. Do not
    reconstruct removed material or attempt to repair unrelated invalid input.
    """
    if suffix.lower() != '.json':
        return redact(text, secrets)
    repaired_tokens = 0
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        parts = re.split(r'("(?:[^"\\]|\\.)*")', text)
        for i in range(0, len(parts), 2):
            parts[i], changed = re.subn(r'[-+\deE.]*\[REDACTED\][-+\deE.]*', 'null', parts[i])
            repaired_tokens += changed
        body = json.loads(''.join(parts))
    count = repaired_tokens
    def clean(value):
        nonlocal count
        if isinstance(value, str):
            result = redact(value, secrets)
            count += int(result != value)
            return result
        if isinstance(value, dict):
            result = {}
            for index, (key, item) in enumerate(value.items()):
                safe_key = redact(key, secrets)
                if safe_key != key:
                    safe_key = f'redacted_field_{index}'
                    count += 1
                    result[safe_key] = '[REDACTED]'
                else:
                    result[safe_key] = clean(item)
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        if type(value) in (int, float) and violations(json.dumps(value), secrets):
            count += 1
            return None
        return value
    safe = clean(body)
    if count == 0:
        return text
    if count and isinstance(safe, dict):
        safe['security_redactions'] = {'withheld_values': count,
            'notice': 'Sensitive material removed. Null may denote a withheld numeric value.'}
    return json.dumps(safe, indent=2, ensure_ascii=False) + '\n'


def report_files(root):
    root = Path(root)
    found = set()
    for name in ('reports', 'work/reports', 'logs'):
        directory = root / name
        if directory.is_dir():
            found.update(p for p in directory.rglob('*')
                         if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)
    for path in root.glob('*REPORT*.md'):
        found.add(path)
    for name in ('AUDIT.md',):
        if (root / name).is_file():
            found.add(root / name)
    work = root / 'work'
    if work.is_dir():
        found.update(p for p in work.rglob('*.log') if p.is_file())
    return sorted(found)


def scan(root):
    secrets = configured_secrets(root)
    findings = []
    paths = report_files(root)
    for path in paths:
        try:
            if not path.resolve().is_relative_to(Path(root).resolve()):
                raise OSError('Report link leaves workspace')
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            findings.append({'path': redact(str(path.relative_to(root)), secrets), 'rules': ['unreadable-report']})
            continue
        reasons = violations(text, secrets)
        if path.suffix.lower() == '.json':
            try:
                json.loads(text)
            except ValueError:
                reasons.append('invalid-json-report')
        if reasons:
            # Never return text, sensitive matches, offsets or surrounding lines.
            findings.append({'path': redact(str(path.relative_to(root)), secrets), 'rules': reasons})
    return {'files_scanned': len(paths), 'findings': findings}
