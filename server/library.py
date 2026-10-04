"""Library promotion, shuffle and idempotent, elapsed-time-checked play accounting."""
import json
import random
import time
import uuid
from .config import DATA, STYLE_MAP, safe_path
from .database import connection, rows, now, event, settings
from .operation_lock import exclusive


def public_track(row):
    d={k:row[k] for k in ['id','style','title','duration','plays','status','created']}
    d['metadata']=json.loads(row['metadata'])
    d['metadata'].update(play_count=row['plays'],status=row['status'])
    return d


def tracks():
    # The room UI lists recent arrivals; it must not serialize a 150 GB archive.
    return [public_track(r) for r in rows("SELECT id,style,title,duration,plays,status,created,metadata FROM tracks WHERE status='ready' ORDER BY created DESC LIMIT 60")]


def choose(style=None,exclude=None):
    sql="SELECT id FROM tracks WHERE status='ready' AND plays < ?"
    args=[settings()['plays_before_retire']]
    if style:
        sql+=' AND style=?'; args.append(style)
    candidates=rows(sql,args)
    candidates=[c for c in candidates if c['id'] != exclude]
    if not candidates:
        return None
    history=[r['track_id'] for r in rows('SELECT track_id FROM plays ORDER BY started DESC LIMIT 150')]
    unseen=[c for c in candidates if c['id'] not in history]
    if unseen:
        candidates=unseen
    elif history:
        # Avoid repeating previous directed edges when a tiny pool forces recent reuse.
        pairs=set(zip(history[1:],history[:-1]))
        allowed=[c for c in candidates if (history[0],c['id']) not in pairs]
        if allowed: candidates=allowed
        age={id:i for i,id in reversed(list(enumerate(history)))}
        oldest=max(age.get(c['id'],150) for c in candidates)
        candidates=[c for c in candidates if age.get(c['id'],150)>=max(0,oldest-8)]
    selected=random.SystemRandom().choice(candidates)['id']
    return public_track(rows('SELECT * FROM tracks WHERE id=?',(selected,))[0])


@exclusive
def write_sidecar(track_id):
    with connection() as db:
        row=db.execute('SELECT * FROM tracks WHERE id=?',(track_id,)).fetchone()
    if not row or row['status']!='ready':return
    path=safe_path(row['path']).with_suffix('.json')
    meta=json.loads(row['metadata'])
    meta.update(play_count=row['plays'],status=row['status'])
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
    tmp.replace(path)


@exclusive
def retire(track_id,reason='played_four_times'):
    with connection() as db:
        row=db.execute('SELECT * FROM tracks WHERE id=?',(track_id,)).fetchone()
        if not row:return False
        db.execute("UPDATE tracks SET status='retiring' WHERE id=?",(track_id,))
    try:
        path=safe_path(row['path'])
        path.unlink(missing_ok=True)
        path.with_suffix('.json').unlink(missing_ok=True)
        with connection() as db:
            db.execute("UPDATE tracks SET status='retired' WHERE id=?",(track_id,))
        event('track_retired',f'{track_id}: {reason}')
        return True
    except OSError as exc:
        event('filesystem_error',f'Retirement pending: {track_id}: {exc}',level='error')
        return False


@exclusive
def start_play(track_id):
    with connection() as db:
        row=db.execute("SELECT id FROM tracks WHERE id=? AND status='ready'",(track_id,)).fetchone()
        if not row:raise ValueError('Track unavailable')
        sid=uuid.uuid4().hex; ts=time.time()
        db.execute('INSERT INTO plays(id,track_id,started,last_ping) VALUES(?,?,?,?)',(sid,track_id,ts,ts))
    return sid


@exclusive
def ping_play(session_id,playing=True,finish=False,reason='ended'):
    retire_id=None; count=False
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT p.*,t.duration,t.plays FROM plays p JOIN tracks t ON t.id=p.track_id WHERE p.id=?',(session_id,)).fetchone()
        if not row or row['ended'] is not None:return {'counted':False}
        ts=time.time()
        elapsed=max(0,min(8,ts-row['last_ping'])) if playing else 0
        listened=row['listened']+elapsed
        db.execute('UPDATE plays SET listened=?,last_ping=? WHERE id=?',(listened,ts,session_id))
        if finish:
            count=reason=='ended' and listened>=row['duration']*.88
            db.execute('UPDATE plays SET ended=?,counted=?,reason=? WHERE id=?',(ts,int(count),reason,session_id))
            if count:
                db.execute('UPDATE tracks SET plays=plays+1 WHERE id=?',(row['track_id'],))
                if row['plays']+1>=settings()['plays_before_retire']:
                    retire_id=row['track_id']
    if count:
        if retire_id:retire(retire_id)
        else:write_sidecar(row['track_id'])
    return {'counted':count,'listened':listened,'retired':bool(retire_id)}


@exclusive
def maintenance():
    for r in rows("SELECT id FROM tracks WHERE status='retiring'"):
        retire(r['id'],'retry_pending_deletion')
    # Repair missing files without blocking continued playback.
    for r in rows("SELECT id,path FROM tracks WHERE status='ready'"):
        if not safe_path(r['path']).exists():
            with connection() as db:db.execute("UPDATE tracks SET status='missing' WHERE id=?",(r['id'],))
            event('filesystem_error',f'Missing library file: {r["id"]}',level='error')
