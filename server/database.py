"""SQLite WAL transactions, durable job and play history, rotating structured logs."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from .config import DATA, DEFAULTS, STYLE_MAP, setup_dirs


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    db = sqlite3.connect(DATA / 'library.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(recover=True):
    setup_dirs()
    with connection() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tracks(
          id TEXT PRIMARY KEY, style TEXT NOT NULL, title TEXT NOT NULL,
          path TEXT NOT NULL, duration REAL NOT NULL, bytes INTEGER NOT NULL,
          plays INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ready',
          created TEXT NOT NULL, metadata TEXT NOT NULL, embedding BLOB, fingerprint BLOB);
        CREATE INDEX IF NOT EXISTS tracks_pool ON tracks(status,style);
        CREATE INDEX IF NOT EXISTS tracks_created ON tracks(created DESC);
        CREATE INDEX IF NOT EXISTS tracks_sha256 ON tracks(json_extract(metadata,'$.qc.final.sha256'));
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY, style TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL,
          updated TEXT NOT NULL, params TEXT NOT NULL, attempts INTEGER DEFAULT 0,
          error_code TEXT, error TEXT, track_id TEXT, available_at REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS plays(
          id TEXT PRIMARY KEY, track_id TEXT NOT NULL, started REAL NOT NULL,
          last_ping REAL NOT NULL, listened REAL NOT NULL DEFAULT 0,
          ended REAL, counted INTEGER NOT NULL DEFAULT 0, reason TEXT);
        CREATE INDEX IF NOT EXISTS plays_started ON plays(started DESC);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, time TEXT NOT NULL, level TEXT NOT NULL,
          code TEXT NOT NULL, job_id TEXT, detail TEXT NOT NULL);
        ''')
        columns={r['name'] for r in db.execute('PRAGMA table_info(events)')}
        for name in ['model_variant','model_name']:
            if name not in columns:db.execute(f'ALTER TABLE events ADD COLUMN {name} TEXT')
        # Resolve historical entries from their own jobs, not today's style recipe.
        db.execute("UPDATE events SET model_variant=(SELECT json_extract(params,'$.model_variant') FROM jobs WHERE jobs.id=events.job_id) WHERE model_variant IS NULL AND job_id IS NOT NULL")
        from .models import MODELS
        for variant,spec in MODELS.items():
            db.execute('UPDATE events SET model_name=? WHERE model_variant=? AND model_name IS NULL',(spec['name'],variant))
        registered={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
        for key, value in DEFAULTS.items():
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (key,json.dumps(value)))
        from .locks import InferenceLease
        try:
            with InferenceLease():
                if recover:db.execute("UPDATE jobs SET status='queued',error_code='interrupted',error='Recovered after restart',updated=? WHERE status IN ('running','processing')",(now(),))
        except BlockingIOError:
            pass
    from .preferences import initialize_config
    initialize_config(registered)
    # Resolve custom identities only after validated user styles have been loaded.
    with connection() as db:
        placeholders=','.join('?' for _ in STYLE_MAP)
        db.execute(f"UPDATE jobs SET status='cancelled',error_code='style_retired',error='Category removed; submit a current recipe',updated=? WHERE style NOT IN ({placeholders}) AND status='queued'",(now(),*STYLE_MAP))
    # Only shipped filenames are repaired; replaced bytes and user imports survive.
    from .config import PROJECT
    from .builtin_assets import repair_builtins
    repair_builtins(PROJECT/'builtin-ambience',DATA/'Ambience')
    from .config import library_root
    library_root().mkdir(parents=True,exist_ok=True)
    log = logging.getLogger('ambient')
    if not log.handlers:
        handler = RotatingFileHandler(DATA / '.log/events.jsonl',maxBytes=5_000_000,backupCount=5,encoding='utf8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        log.addHandler(handler)
        log.setLevel(logging.INFO)


def settings():
    with connection() as db:
        return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}


def event(code, detail, job_id=None, level='info'):
    record = dict(time=now(),level=level,code=code,job_id=job_id,detail=detail)
    from .models import MODELS
    variant=None
    if job_id:
        job=rows("SELECT json_extract(params,'$.model_variant') variant FROM jobs WHERE id=?",(job_id,))
        if job:variant=job[0]['variant']
    record.update(model_variant=variant,model_name=MODELS.get(variant,{}).get('name',variant))
    logging.getLogger('ambient').info(json.dumps(record,ensure_ascii=False))
    with connection() as db:
        db.execute('INSERT INTO events(time,level,code,job_id,detail,model_variant,model_name) VALUES(?,?,?,?,?,?,?)',tuple(record.values()))
        db.execute('DELETE FROM events WHERE id < (SELECT MAX(id)-10000 FROM events)')


def rows(sql, args=()):
    with connection() as db:
        return [dict(r) for r in db.execute(sql,args)]
