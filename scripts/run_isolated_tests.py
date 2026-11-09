"""Run reviewed tests in a disposable checkout copy without real credentials.

Python filesystem mutations are confined to the copy. External and model
requests are denied in the runner and dashboard subprocesses. This is a
verification harness, not a permission to launch a production trading process.
The copy is retained for inspection; this script never removes it.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_TESTS = {
    'test_binance_testnet_live_ping_and_server_time',
    'test_binance_testnet_live_symbol_info_and_filters',
    'test_binance_testnet_live_ticker_price',
    'test_binance_testnet_auth_failure_semantics',
    'test_09_listings_filter_unlisted_tokens',
}
GUARD = r'''
import sys, os, pathlib, ipaddress, tempfile, urllib.parse, urllib.request
_base = pathlib.Path(os.environ['ZILLERS_AUDIT_SANDBOX']).resolve()
tempfile.tempdir = str(_base / 'tmp')
def _inside(p):
    if isinstance(p, int) or p is None: return True
    if str(p).lower() in ('nul', '/dev/null'): return True
    if str(p).startswith('file:'):
        p = urllib.request.url2pathname(urllib.parse.urlsplit(str(p)).path)
    try: return pathlib.Path(os.fsdecode(p)).resolve().is_relative_to(_base)
    except Exception: return False
def _audit(event, args):
    if event == 'open':
        p, mode, flags = args
        writing = (isinstance(mode, str) and any(x in mode for x in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and not _inside(p): raise PermissionError('Audit: outside-copy write denied')
    elif event == 'sqlite3.connect':
        if str(args[0]) != ':memory:' and not _inside(args[0]):
            raise PermissionError('Audit: outside-copy database denied')
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime'):
        if not _inside(args[0]): raise PermissionError('Audit: outside-copy mutation denied')
    elif event in ('os.rename', 'os.replace'):
        if not _inside(args[0]) or not _inside(args[1]):
            raise PermissionError('Audit: outside-copy rename denied')
    elif event == 'urllib.Request':
        url = urllib.parse.urlsplit(args[0])
        if url.hostname not in ('localhost', '127.0.0.1', '::1') or url.port == 11434:
            raise OSError('Audit: external/model request denied')
    elif event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple):
            try: local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError: local = address[0] == 'localhost'
            if not local or address[1] == 11434:
                raise OSError('Audit: external/model connection denied')
    elif event == 'socket.getaddrinfo':
        if args[0] not in ('localhost', '127.0.0.1', '::1', None):
            raise OSError('Audit: external DNS denied')
sys.addaudithook(_audit)
'''


def prepare():
    destination = Path(tempfile.mkdtemp(prefix='zillers-phase-audit-'))
    files = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().split('\0')
    for name in set(files):
        if not name:
            continue
        source, target = ROOT / name, destination / name
        if source.is_file() and not source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    # Historical fixture only. No account, order, session or credential DB is copied.
    archive = ROOT / 'work/runtime/crypto_candles.db'
    if archive.is_file():
        target = destination / 'work/runtime/crypto_candles.db'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, target)
    (destination / 'tmp').mkdir()
    (destination / 'sitecustomize.py').write_text(GUARD, encoding='utf-8')
    plugin = (
        'import pytest\n'
        f'EXTERNAL = {EXTERNAL_TESTS!r}\n'
        'def pytest_collection_modifyitems(items):\n'
        '    for item in items:\n'
        '        if item.originalname in EXTERNAL:\n'
        '            item.add_marker(pytest.mark.skip(reason="NOT RUN: external service not authorized"))\n'
    )
    (destination / 'audit_pytest_plugin.py').write_text(plugin, encoding='utf-8')
    environment = dict(os.environ)
    for key in list(environment):
        if any(word in key.upper() for word in (
                'SECRET', 'TOKEN', 'PASSWORD', 'PASSCODE', 'API_KEY', 'OLLAMA',
                'TELEGRAM', 'WEBHOOK', 'DISCORD', 'TRADING_MODE', 'ADMIN_EMAIL',
                'INVITE_CODE', 'SIGNUP_MODE', 'GOVERNOR_STATE_DB')):
            environment.pop(key, None)
    environment.update(
        PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        PYTHONPATH=str(destination), ZILLERS_AUDIT_SANDBOX=str(destination),
        TEMP=str(destination / 'tmp'), TMP=str(destination / 'tmp'),
        ADMIN_INITIAL_PASSWORD='DisposableAuditOnly2026!#',
        ADMIN_EMAIL='admin@zillers.local', LIVE_TRADING='false',
        SIGNUP_MODE='closed', ACCOUNT_SIZE_USD='1000', PYTHONIOENCODING='utf-8',
    )
    return destination, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stream', action='store_true', help='Stream isolated pytest progress')
    parser.add_argument('tests', nargs='*', default=['cryptoscope/tests'])
    args = parser.parse_args()
    destination, environment = prepare()
    command = [sys.executable, '-B', '-m', 'pytest', *args.tests,
               '-p', 'no:cacheprovider', '-p', 'audit_pytest_plugin', '-ra',
               '--tb=short', '--log-file', str(destination / 'pytest.log')]
    print('DISPOSABLE_COPY=' + str(destination), flush=True)
    print('COMMAND=' + json.dumps(command), flush=True)
    if args.stream:
        command[5:5] = ['-vv', '-s']
        with (destination / 'test-output.txt').open('w', encoding='utf-8') as output:
            process = subprocess.Popen(command, cwd=destination, env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', bufsize=1)
            for line in process.stdout:
                output.write(line)
                output.flush()
                print(line, end='', flush=True)
            result_code = process.wait()
    else:
        result = subprocess.run(command, cwd=destination, env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8')
        (destination / 'test-output.txt').write_text(result.stdout, encoding='utf-8')
        print(result.stdout, flush=True)
        result_code = result.returncode
    print('EXIT_CODE=' + str(result_code), flush=True)
    return result_code


if __name__ == '__main__':
    raise SystemExit(main())
