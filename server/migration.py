"""Copy -> hash verify -> atomic DB switch -> remove verified source files.

Models, database, logs and ambience stay in DATA. Only MusicLib is movable.
The durable journal permits retry after interruption without overwriting a
destination that belongs to somebody else.
"""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from .config import DATA,library_root
from .database import connection,rows,settings,event,now
from .locks import InferenceLease
from .operation_lock import gate
from .paths import is_link,reject_links

CHUNK=4*1024*1024

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def contained(root,relative):
    reject_links(root/relative)
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or path==root:raise ValueError('Migration path escapes owned folder')
    return path


class LibraryMigration:
    def __init__(self):
        self.journal=DATA/'library-migration.json';self.lock=threading.RLock()
        self.state={'active':False,'phase':'idle'};self.thread=None;self.started=0;self.last_save=0

    @property
    def active(self):return self.state.get('active',False)

    def snapshot(self):
        with self.lock:
            state={k:v for k,v in self.state.items() if k!='files'}
            state['library_path']=str(library_root())
            total=state.get('total_bytes',0)*2;done=state.get('work_bytes',0)
            state['progress']=100 if state['phase']=='done' else min(99,100*done/max(1,total))
            elapsed=time.monotonic()-self.started if self.started else 0
            state['eta_seconds']=round((total-done)/(done/elapsed)) if done>0 and elapsed>1 and total>done else None
            return state

    def persist(self,force=False,**values):
        with self.lock:
            self.state.update(values)
            if not force and time.monotonic()-self.last_save<.5:return
            self.last_save=time.monotonic();self.journal.parent.mkdir(parents=True,exist_ok=True)
            temp=self.journal.with_suffix('.tmp');temp.write_text(json.dumps(self.state,ensure_ascii=False),encoding='utf8')
            temp.replace(self.journal)

    def restore(self):
        if not self.journal.exists():return
        raw=self.journal.read_bytes()
        try:
            state=json.loads(raw)
            phases=('idle','waiting','scanning','copying','verifying','switching','cleaning','done','failed','interrupted')
            if not isinstance(state,dict) or state.get('phase') not in phases:raise ValueError('Invalid migration state')
            for key in ('total_bytes','work_bytes'):
                value=state.get(key,0)
                if type(value)!=int or not 0<=value<2**63:raise ValueError('Invalid migration progress')
            if state.get('recovery_error'):
                self.state=state;self.state['active']=False;return
            if state['phase'] not in ('idle','done'):
                if not all(isinstance(state.get(k),str) and Path(state[k]).is_absolute() for k in ('source','destination')):
                    raise ValueError('Invalid migration paths')
                source,destination=Path(state['source']).resolve(),Path(state['destination']).resolve()
                if source==destination or source.is_relative_to(destination) or destination.is_relative_to(source):
                    raise ValueError('Migration paths overlap')
                if not isinstance(state.get('files'),list):raise ValueError('Invalid migration file list')
                committed=library_root()==Path(state['destination']).resolve()
                for item in state['files']:
                    relative=item['relative']
                    if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
                        raise ValueError('Invalid migration file path')
                    if not isinstance(item['bytes'],int) or item['bytes']<0:raise ValueError('Invalid migration file size')
                    if committed and not re.fullmatch('[a-f0-9]{64}',item.get('sha256','')):
                        raise ValueError('Committed migration is missing file checksums')
            self.state=state
        except (ValueError,TypeError,KeyError,UnicodeError) as exc:
            backup=self.journal.with_name('library-migration.rejected-'+hashlib.sha256(raw).hexdigest()[:16]+'.json')
            if not backup.exists():backup.write_bytes(raw)
            self.state={'active':False,'phase':'failed','recovery_error':True,
                        'error':'迁移记录损坏，已保留原件；继续使用数据库登记的曲库。迁移两端文件均未删除。'}
            self.persist(True)
            return
        self.state['active']=False
        if self.state.get('phase') not in ('done','idle'):
            # Committed moves finish cleanup before the producer starts again.
            if library_root()==Path(self.state['destination']).resolve():
                try:self.start(self.state['destination'])
                except (ValueError,OSError) as exc:self.persist(True,active=False,phase='failed',error=str(exc))
            else:self.persist(True,phase='interrupted',error='上次迁移被中断，原库仍可使用；可在曲库管理中重试。')

    def validate(self,destination):
        raw=Path(destination)
        if not raw.is_absolute():raise ValueError('请选择绝对目录路径')
        target=raw.resolve();source=library_root()
        retry=self.state.get('destination')==str(target) and self.state.get('phase') not in ('idle','done')
        committed=retry and source==target
        if committed:source=Path(self.state['source']).resolve()
        if target==source or target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError('新旧曲库不能相同，也不能互相包含')
        if target==DATA or any(target.is_relative_to(DATA/n) for n in ('models','staging','.log','Ambience')):
            raise ValueError('不能把模型、日志或临时目录作为曲库')
        reject_links(raw);reject_links(Path(self.state['source']) if committed else Path(settings()['library_path']));reject_links(source)
        if target.exists():
            if not target.is_dir():raise ValueError('目标不是目录')
            marker=target/'.ambient-library-move.json'
            if any(target.iterdir()) and not (committed or (retry and marker.is_file() and json.loads(marker.read_text())['id']==self.state.get('id'))):
                raise ValueError('请选择空目录；不会覆盖目标目录中的已有文件')
        return source,target,retry,committed

    def start(self,destination):
        with self.lock:
            if self.active:raise ValueError('已有曲库迁移正在进行')
            source,target,retry,committed=self.validate(destination)
            if not retry:self.state={'id':uuid.uuid4().hex,'source':str(source),'destination':str(target),'files':[]}
            self.started=time.monotonic()
            self.persist(True,active=True,phase='waiting',error=None,work_bytes=0)
            self.thread=threading.Thread(target=self.run,args=(source,target,committed),daemon=True)
            self.thread.start()
            return self.snapshot()

    def scan(self,source,target):
        reject_links(source);reject_links(target)
        previous={f['relative'] for f in self.state.get('files',[])}
        # Retry accepts only files written by this exact interrupted operation.
        if target.exists():
            allowed=previous|{f+'.part' for f in previous}|{'.ambient-library-move.json'}
            for p in target.rglob('*'):
                if is_link(p):raise ValueError('目标中出现了链接，已停止迁移')
                if p.is_file() and p.relative_to(target).as_posix() not in allowed:raise ValueError('目标中出现了其他文件，已停止迁移')
        files=[]
        for p in source.rglob('*'):
            if is_link(p):raise ValueError('源曲库含链接，无法安全迁移')
            if p.is_file():files.append({'relative':p.relative_to(source).as_posix(),'bytes':p.stat().st_size})
        files.sort(key=lambda f:f['relative'])
        return files

    def run(self,source,target,committed=False):
        try:
            # Never hold the media gate while waiting for inference: an active
            # generator needs that gate to finish publishing its last result.
            while True:
                try:
                    lease=InferenceLease();lease.__enter__();break
                except BlockingIOError:time.sleep(.25)
            try:
                with gate:self.transfer(source,target,committed)
            finally:lease.__exit__(None,None,None)
        except Exception as exc:
            self.persist(True,active=False,phase='failed',error=str(exc))
            event('library_migration_error',str(exc),level='error')

    def transfer(self,source,target,committed):
        if not committed:
            self.persist(True,phase='scanning')
            files=self.scan(source,target);total=sum(f['bytes'] for f in files)
            nearest=target
            while not nearest.exists():nearest=nearest.parent
            if shutil.disk_usage(nearest).free<total+settings()['minimum_free_gb']*1e9:
                raise OSError('目标磁盘空间不足，需容纳完整曲库并保留磁盘余量')
            # Persist the complete owned path list before creating any destination file.
            self.persist(True,files=files,total_bytes=total,file_count=len(files),work_bytes=0)
            target.mkdir(parents=True,exist_ok=True)
            (target/'.ambient-library-move.json').write_text(json.dumps({'id':self.state['id']}),encoding='utf8')
            with connection() as db:db.execute("UPDATE plays SET ended=?,reason='library_migration' WHERE ended IS NULL",(time.time(),))
            done=0
            for index,item in enumerate(files):
                old=contained(source,item['relative']);new=contained(target,item['relative']);new.parent.mkdir(parents=True,exist_ok=True)
                temp=new.with_name(new.name+'.part');hasher=hashlib.sha256()
                self.persist(True,phase='copying',current_file=item['relative'],files_done=index)
                with old.open('rb') as inp,temp.open('wb') as out:
                    while chunk:=inp.read(CHUNK):
                        out.write(chunk);hasher.update(chunk);done+=len(chunk);self.persist(work_bytes=done)
                    out.flush();os.fsync(out.fileno())
                if temp.stat().st_size!=item['bytes']:raise OSError('源文件在复制期间发生变化')
                item['sha256']=hasher.hexdigest();temp.replace(new);self.persist(True)
            self.persist(True,phase='verifying')
            for item in files:
                new=contained(target,item['relative']);hasher=hashlib.sha256()
                with new.open('rb') as inp:
                    while chunk:=inp.read(CHUNK):hasher.update(chunk);done+=len(chunk);self.persist(work_bytes=done,current_file=item['relative'])
                if hasher.hexdigest()!=item['sha256']:raise OSError('复制校验失败：'+item['relative'])
            self.persist(True,phase='switching')
            with connection() as db:
                db.execute('BEGIN IMMEDIATE')
                for row in db.execute('SELECT id,path FROM tracks').fetchall():
                    old=Path(row['path']).resolve()
                    if old.is_relative_to(source):db.execute('UPDATE tracks SET path=? WHERE id=?',(str(target/old.relative_to(source)),row['id']))
                db.execute("UPDATE settings SET value=? WHERE key='library_path'",(json.dumps(str(target)),))
            from .preferences import sync_library_path
            sync_library_path(target)
            # Startup uses the atomic library_path value to detect a committed move,
            # even if the process stopped before the next journal update.
        self.persist(True,phase='cleaning')
        for item in self.state['files']:
            old=contained(source,item['relative']);new=contained(target,item['relative'])
            if not old.exists():continue
            if not new.is_file() or digest(new)!=item['sha256'] or digest(old)!=item['sha256']:
                raise OSError('旧文件保留：迁移后校验内容发生变化 '+item['relative'])
            old.unlink()
        if source.exists():
            for folder in sorted((p for p in source.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                if folder.resolve().is_relative_to(source):folder.rmdir()
            source.rmdir()
        (target/'.ambient-library-move.json').unlink(missing_ok=True)
        self.persist(True,active=False,phase='done',current_file='',finished=now())
        event('library_moved',f'{source} -> {target}; {len(self.state["files"])} files verified')


manager=LibraryMigration()
