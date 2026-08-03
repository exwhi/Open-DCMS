"""Simple SQLite-backed offline queue for Agent.

Features:
- enqueue(data) -> id
- dequeue(batch=1) -> list of (id, data)
- ack(id) -> remove from queue
- purge() -> clear queue (testing)

This implementation opens a short-lived connection per operation to
minimize locking issues on Windows.
"""
from __future__ import annotations

import sqlite3
import json
import time
from typing import List, Tuple, Optional

DEFAULT_DB = 'agent_offline.db'


class OfflineQueue:
    def __init__(self, path: str = DEFAULT_DB, timeout: float = 5.0):
        self.path = path
        self.timeout = timeout
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)

    def _init_db(self):
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created REAL NOT NULL,
                payload TEXT NOT NULL
            )
            """)
            conn.commit()
        finally:
            conn.close()

    def enqueue(self, obj: dict) -> int:
        raw = json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
        now = time.time()
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute('BEGIN IMMEDIATE')
            cur.execute('INSERT INTO queue (created, payload) VALUES (?, ?)', (now, raw))
            rowid = cur.lastrowid
            conn.commit()
            return rowid
        finally:
            conn.close()

    def dequeue(self, batch: int = 1) -> List[Tuple[int, dict]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute('BEGIN IMMEDIATE')
            cur.execute('SELECT id, payload FROM queue ORDER BY id LIMIT ?', (batch,))
            rows = cur.fetchall()
            items: List[Tuple[int, dict]] = []
            for rid, payload in rows:
                try:
                    items.append((rid, json.loads(payload)))
                except Exception:
                    items.append((rid, {'raw': payload}))
            conn.commit()
            return items
        finally:
            conn.close()

    def ack(self, rid: int) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute('BEGIN IMMEDIATE')
            cur.execute('DELETE FROM queue WHERE id = ?', (rid,))
            conn.commit()
        finally:
            conn.close()

    def purge(self) -> None:
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute('BEGIN IMMEDIATE')
            cur.execute('DELETE FROM queue')
            conn.commit()
        finally:
            conn.close()


def _demo():
    q = OfflineQueue(':memory:')
    q.enqueue({'a': 1})
    print(q.dequeue())


if __name__ == '__main__':
    _demo()
