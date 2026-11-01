"""Persist every stage, including failed runs, to a dedicated SQLite database."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager


class ResearchStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "research.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created REAL, status TEXT, body TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, body):
        run_id = uuid.uuid4().hex
        body.update(run_id=run_id, created_at=time.time(), status="running", stages=[], prompt_version="1")
        self.save(body)
        return body

    def save(self, body):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)",
                       (body["run_id"], body["created_at"], body["status"], json.dumps(body, allow_nan=False)))

    def recent(self, limit=20):
        with self.connect() as db:
            return [{"run_id": r[0], "created_at": r[1], "status": r[2]}
                    for r in db.execute("SELECT id,created,status FROM runs ORDER BY created DESC LIMIT ?", (limit,))]
