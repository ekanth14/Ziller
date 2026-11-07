"""One durable emergency latch. Readers fail closed; only local admin can clear.

This module has no broker, exchange, model, or notification imports. Constructing
a reader never creates or migrates production state. State changes are explicit.
"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[2]


class GovernorState:
    def __init__(self, path=None):
        self._path = Path(path) if path is not None else None

    @property
    def path(self):
        return self._path or Path(os.environ.get('GOVERNOR_STATE_DB') or ROOT / 'work/runtime/governor.db')

    @staticmethod
    def unavailable():
        return {'halted': True, 'action': 'HALT', 'reason': 'GOVERNOR_STATE_UNAVAILABLE',
                'actor': None, 'changed_at': None}

    def snapshot(self):
        if not self.path.is_file():
            return self.unavailable()
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
                db.execute('PRAGMA busy_timeout=5000')
                row = db.execute('SELECT halted,action,reason,actor,changed_at FROM emergency_control WHERE id=1').fetchone()
            if row is None or row[0] not in (0, 1):
                return self.unavailable()
            return dict(zip(('halted', 'action', 'reason', 'actor', 'changed_at'), (bool(row[0]), *row[1:])))
        except (sqlite3.Error, OSError, ValueError):
            return self.unavailable()

    def _write(self, halted, action, reason, actor):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('''CREATE TABLE IF NOT EXISTS emergency_control (
                id INTEGER PRIMARY KEY CHECK(id=1), halted INTEGER NOT NULL CHECK(halted IN (0,1)),
                action TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL,
                changed_at REAL NOT NULL)''')
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT INTO emergency_control VALUES (1,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET halted=excluded.halted,
                action=excluded.action,reason=excluded.reason,actor=excluded.actor,
                changed_at=excluded.changed_at''',
                       (int(halted), action, reason, actor, time.time()))
            db.commit()
        return self.snapshot()

    def halt(self, reason='Emergency halt', actor='local-system', action='HALT'):
        if action not in {'HALT', 'HALT_FLATTEN'}:
            raise ValueError('Invalid emergency action')
        return self._write(True, action, str(reason)[:500], str(actor)[:200])

    def resume_local_admin(self, *, admin_reauthenticated, actor):
        if admin_reauthenticated is not True or not actor:
            raise PermissionError('Local administrator re-authentication required')
        return self._write(False, 'ACTIVE', 'Local administrator re-authenticated', str(actor)[:200])


class PersistentKillSwitch:
    """Attach the durable latch without changing the five-gate governor."""
    def __init__(self, delegate, state=None):
        self.delegate = delegate
        self.state = state or GovernorState()

    @property
    def halted(self):
        return self.state.snapshot()['halted']

    @property
    def action(self):
        return self.state.snapshot()['action']

    @property
    def halted_at(self):
        return self.state.snapshot()['changed_at']

    @property
    def halted_by(self):
        return self.state.snapshot()['actor']

    def execute_kill_switch(self, action, triggered_by, **callbacks):
        self.state.halt('Master emergency halt', triggered_by, action)
        result=self.delegate.execute_kill_switch(action=action, triggered_by=triggered_by, **callbacks)
        if not callbacks:
            result.update(execution_requested=True,execution_confirmed=False,
                execution_note='Durable halt recorded; the execution process must confirm exchange actions separately')
        return result

    def resume_bot(self, admin_reauthenticated, admin_email):
        if admin_reauthenticated is not True:
            raise PermissionError('Local administrator re-authentication required')
        result = self.delegate.resume_bot(admin_reauthenticated=True, admin_email=admin_email)
        self.state.resume_local_admin(admin_reauthenticated=True, actor=admin_email)
        return result
