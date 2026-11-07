"""Shared SQLite connection policy; busy_timeout is applied on every connection."""
from pathlib import Path
import sqlite3

BUSY_TIMEOUT_MS=5000


def connect_database(path, *, readonly=False):
    target=Path(path).resolve().as_uri()+'?mode=ro' if readonly else path
    connection=sqlite3.connect(target,uri=readonly,timeout=BUSY_TIMEOUT_MS/1000)
    connection.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')
    if not readonly:connection.execute('PRAGMA journal_mode=WAL')
    return connection
