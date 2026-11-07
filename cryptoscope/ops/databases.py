"""Read-only SQLite inventory and locally verified online backups. No deletions."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from cryptoscope.storage.sqlite import connect_database


def database_paths(root,include_backups=True):
    root=Path(root).resolve()
    return sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in {'.db','.sqlite','.sqlite3'}
        and '.git' not in p.parts and (include_backups or 'backups' not in p.relative_to(root).parts))


def database_info(path):
    with closing(connect_database(path,readonly=True)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts={}
        for name in tables:
            identifier='"'+name.replace('"','""')+'"'
            counts[name]=db.execute('SELECT count(*) FROM '+identifier).fetchone()[0]
        return dict(journal_mode=db.execute('PRAGMA journal_mode').fetchone()[0],
            connection_busy_timeout_ms=db.execute('PRAGMA busy_timeout').fetchone()[0],
            user_version=db.execute('PRAGMA user_version').fetchone()[0],
            schema_version=db.execute('PRAGMA schema_version').fetchone()[0],tables=counts)


def inventory(root):
    root=Path(root).resolve();results=[]
    for p in database_paths(root):
        try:results.append(dict(path=str(p.relative_to(root)),**database_info(p)))
        except (sqlite3.Error,OSError) as error:results.append(dict(path=str(p.relative_to(root)),error_type=type(error).__name__))
    users=root/'work/runtime/users.db';sessions=[]
    if users.exists():
        with closing(connect_database(users,readonly=True)) as db:
            # Display row identity, role and expiry only. Never session values.
            rows=db.execute('SELECT s.id,u.role,s.created_at,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.expires_at>?',(time.time(),)).fetchall()
            sessions=[dict(row_id=r[0],role=r[1],created_at=r[2],expires_at=r[3]) for r in rows]
    return dict(databases=results,active_sessions=sessions,active_session_count=len(sessions),
                timeout_policy='5000 ms per connection; observed inventory connection setting does not prove other callers set it')


def logical_fingerprint(db):
    """Hash a consistent SQLite snapshot logically; never return row contents."""
    digest=hashlib.sha256()
    for line in db.iterdump():digest.update(line.encode('utf-8'));digest.update(b'\n')
    return digest.hexdigest()


def backup_and_verify(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for source in database_paths(root,include_backups=False):
        relative=source.relative_to(root)
        if destination in source.parents:continue
        target=destination/'snapshot'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        with closing(connect_database(source,readonly=True)) as src,closing(connect_database(target)) as backup:
            src.backup(backup,pages=256,sleep=.02)
        restored=destination/'restore-check'/relative
        restored.parent.mkdir(parents=True,exist_ok=True)
        with closing(connect_database(target,readonly=True)) as backup,closing(connect_database(restored)) as restore:
            backup.backup(restore)
            integrity=restore.execute('PRAGMA integrity_check').fetchone()[0]
            same=logical_fingerprint(backup)==logical_fingerprint(restore)
        manifest.append(dict(path=str(relative),integrity=integrity,logical_restore_equal=same,
                             snapshot=database_info(target)))
    result=dict(created_at=datetime.now(timezone.utc).isoformat(),databases=manifest,
                passed=all(m['integrity']=='ok' and m['logical_restore_equal'] for m in manifest),
                note='Per-database consistent backup; not an atomic cross-database transaction. Restores retained separately; production never overwritten.')
    (destination/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
