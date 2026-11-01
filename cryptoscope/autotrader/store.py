import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager


class ProcessLock:
    def __init__(self,path):
        self.path=Path(path)
        self.stream=None

    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b')
        if self.path.stat().st_size==0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise RuntimeError('An autotrader process already owns this paper account') from error
        return self

    def __exit__(self,*args):
        if self.stream:
            self.stream.close()


class BotStore:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'autotrader.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runtime (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY CHECK(id=1), stop_requested INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (key TEXT PRIMARY KEY, id TEXT UNIQUE, created REAL, status TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, kind TEXT, body TEXT);
                INSERT OR IGNORE INTO commands VALUES (1,0);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def runtime(self,body):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO runtime VALUES (1,?)',(json.dumps(body,allow_nan=False),))

    def request_stop(self,value=True):
        with self.connect() as db:
            db.execute('UPDATE commands SET stop_requested=? WHERE id=1',(int(value),))

    def stopping(self):
        with self.connect() as db:
            return bool(db.execute('SELECT stop_requested FROM commands WHERE id=1').fetchone()[0])

    def claim(self,key,body):
        body={**body,'run_id':uuid.uuid4().hex,'created_at':time.time(),'status':'running'}
        try:
            with self.connect() as db:
                db.execute('INSERT INTO decisions VALUES (?,?,?,?,?)',
                    (key,body['run_id'],body['created_at'],body['status'],json.dumps(body,allow_nan=False)))
            return body
        except sqlite3.IntegrityError:
            return None

    def save(self,body):
        with self.connect() as db:
            db.execute('UPDATE decisions SET status=?,body=? WHERE id=?',
                       (body['status'],json.dumps(body,allow_nan=False),body['run_id']))

    def event(self,kind,body):
        with self.connect() as db:
            db.execute('INSERT INTO events (created,kind,body) VALUES (?,?,?)',
                       (time.time(),kind,json.dumps(body,allow_nan=False)))

    def abandon_inflight(self):
        with self.connect() as db:
            rows=db.execute("SELECT id,body FROM decisions WHERE status='running'").fetchall()
            for run_id,text in rows:
                body=json.loads(text)
                body.update(status='abandoned',finished_at=time.time(),execution={'status':'discarded_after_restart'})
                db.execute('UPDATE decisions SET status=?,body=? WHERE id=?',('abandoned',json.dumps(body),run_id))

    def snapshot(self):
        with self.connect() as db:
            row=db.execute('SELECT body FROM runtime WHERE id=1').fetchone()
            runtime=json.loads(row[0]) if row else {'state':'stopped'}
            decisions=[json.loads(row[0]) for row in db.execute('SELECT body FROM decisions ORDER BY created DESC LIMIT 20')]
            events=[{'created_at':r[0],'kind':r[1],'body':json.loads(r[2])} for r in db.execute('SELECT created,kind,body FROM events ORDER BY id DESC LIMIT 20')]
            return {'runtime':runtime,'decisions':decisions,'events':events,'stop_requested':self.stopping()}
