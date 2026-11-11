import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import ConfigFields


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Database:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        try:
            # Reserve the single writer before read-modify-write: safe for parallel deliveries.
            con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_key TEXT UNIQUE, data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    timestamp TEXT NOT NULL, type TEXT NOT NULL, text TEXT NOT NULL, received_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_client ON messages(client_id, timestamp, id);
                CREATE TABLE IF NOT EXISTS statuses (
                    message_id TEXT NOT NULL, status TEXT NOT NULL, timestamp TEXT NOT NULL,
                    PRIMARY KEY(message_id, status, timestamp)
                );
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, expires REAL NOT NULL, password_fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (ip_hash TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS login_attempt_time ON login_attempts(at);
            ''')
            defaults = {'revision': '0', 'cfg_version': '1', 'fu': '0', 'cfg': encode(ConfigFields().model_dump())}
            con.executemany('INSERT OR IGNORE INTO meta(key,value) VALUES (?,?)', defaults.items())


def bump(con):
    con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def meta(con, key):
    return con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()[0]


def get_client(con, client_id):
    row = con.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(404, 'Cliente não encontrado.')
    return row, json.loads(row['data'])


def serialize_client(con, row):
    data = json.loads(row['data'])
    messages = con.execute('SELECT * FROM messages WHERE client_id=? ORDER BY timestamp,id', (row['id'],)).fetchall()
    # Old local chat entries are explicitly marked as legacy, never called received via API.
    chat = list(data.pop('legacy_chat', []))
    hist = list(data.get('hist', []))
    for m in messages:
        chat.append({'id': m['id'], 'm': m['text'], 'me': False, 'at': m['timestamp'], 'type': m['type'], 'source': 'whatsapp'})
        hist.append({'d': m['timestamp'][:10], 'at': m['timestamp'], 't': 'Mensagem recebida no WhatsApp (' + m['type'] + ')'})
    data['hist'] = sorted(hist, key=lambda h: h.get('at', h.get('d', '')))
    return {**data, 'id': row['id'], 'version': row['version'], 'chat': chat}


def new_client(fields, now=None):
    now = now or utcnow()
    return {**fields, 'stage': 'novos', 'closed': 0, 'last': now[:10], 'next': 'Fazer primeiro contato',
            'follow': None, 'reason': '', 'endDate': '', 'hist': [{'d': now[:10], 'at': now, 't': 'Cliente cadastrado'}]}


def persist(con, client_id, data, phone_key=None):
    con.execute('UPDATE clients SET data=?,phone_key=?,version=version+1 WHERE id=?',
                (encode(data), phone_key, client_id))
    bump(con)
