"""Bounded persistent producer: isolated jobs, backoff and shared storage budget."""
import json
import hashlib
import os
import random
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
import numpy as np
from .config import DATA, PROJECT, PYTHON, SA3_PYTHON, STYLE_MAP, safe_path, library_root, model_root as configured_model_root
from .database import rows, connection, settings, event, now
from .embedding import compare
from .library import maintenance
from .locks import InferenceLease
from .models import MODELS
from .tonality import MAJOR_KEYS, condition
from .operation_lock import gate,exclusive
from .migration import manager as migration


@exclusive
def enqueue(style='lofi',duration=None):
    if migration.active:raise ValueError('Library migration in progress')
    cfg=settings()
    from .provisioning import snapshot
    if snapshot()['active']:raise ValueError('Model download or verification is in progress')
    if style not in STYLE_MAP:raise ValueError('Unknown style')
    if len(rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"))>=10:
        raise ValueError('Queue full')
    spec=STYLE_MAP[style]; rnd=random.SystemRandom(); id=uuid.uuid4().hex
    p=dict(style=style,prompt=rnd.choice(spec['prompts']),bpm=rnd.randint(*spec['bpm']) if spec.get('bpm') else None,
           prompt_revision=spec.get('prompt_revision','2026-09-24-initial'),model_variant=spec.get('model_variant','acestep-v15-turbo'),
           key=rnd.choice(spec.get('keys',MAJOR_KEYS)),timesignature=spec.get('timesignature','4'),
           seed=rnd.randrange(1,2**31),duration=duration or cfg['duration'],vram_gb=cfg['vram_gb'],lm_enabled=spec.get('lm_enabled',False),encoding=spec.get('encoding',{'codec':'opus','bitrate_kbps':128}))
    p['tonal_policy']=spec.get('tonal_policy','major-v6')
    p['shift']=spec.get('shift',1.0)
    p['prompt']=p['prompt'].replace('{bpm}',str(p['bpm'])).replace('{key}',p['key'])
    if p['tonal_policy']=='major-v6':
        if p['model_variant']=='stable-audio-3-medium':
            # Keep upstream AudioSparx TrackType at the beginning; do not inject
            # the cafe-specific quiet-energy wording into fast Artcore.
            p['prompt']+=f' Entirely in {p["key"]}, bright major harmony throughout, stable major tonic and affirmative phrase endings; no minor-key sections or melancholy mood.'
        else:p['prompt']=condition(p['prompt'],p['key'])
    if p['model_variant']=='stable-audio-3-medium':
        p['duration']=max(120,min(180,p['duration']))
        if style=='guzheng':p['key']='Chinese gong mode / major pentatonic (prompt only)'
    with connection() as db:
        db.execute('INSERT INTO jobs(id,style,status,created,updated,params) VALUES(?,?,?,?,?,?)',(id,style,'queued',now(),now(),json.dumps(p)))
    event('job_queued',style,id)
    return id


def refill_style(counts, enabled, weights=None):
    """Weighted fair fill by playable track counts, independent of encoding.

    Existing excess is consumed normally, never deleted just to rebalance.
    Disabled styles keep their files but receive no automatic new jobs.
    """
    weights=weights or {s:spec['weight'] for s,spec in STYLE_MAP.items()}
    eligible=[s for s in enabled if weights.get(s,0)>0]
    if not eligible:return None
    return min(eligible, key=lambda style: counts.get(style, 0) / weights[style])


def style_retry_after(style):
    """A repeatedly rejected recipe must not monopolize the shared producer."""
    spec=STYLE_MAP[style]
    recent=rows("SELECT status,error_code,updated FROM jobs WHERE style=? AND json_extract(params,'$.model_variant')=? AND json_extract(params,'$.prompt_revision')=? AND status IN ('done','failed') ORDER BY created DESC LIMIT 3",(style,spec.get('model_variant','acestep-v15-turbo'),spec.get('prompt_revision','2026-09-24-initial')))
    if len(recent)<3 or any(r['status']!='failed' or r['error_code'] not in ('qc_rejection','generation_error') for r in recent):return 0
    return datetime.fromisoformat(recent[0]['updated']).timestamp()+1800


def refill_plan():
    cfg=settings()
    pool=rows("SELECT style,COUNT(*) count FROM tracks WHERE status='ready' GROUP BY style")
    counts={r['style']:r['count'] for r in pool};total=sum(counts.values());weights=cfg['style_weights'];weight_total=sum(weights.values())
    eligible=[s for s in cfg['enabled_styles'] if s in STYLE_MAP and weights.get(s,0)>0 and style_retry_after(s)<=time.time()]
    order=sorted(eligible,key=lambda s:counts.get(s,0)/weights[s])
    return {'basis':'tracks','enabled':cfg['auto_generate'],'priority':[
        {'style':s,'name':STYLE_MAP[s]['name'],'count':counts.get(s,0),'current_percent':100*counts.get(s,0)/max(1,total),
         'target_percent':100*weights[s]/max(1,weight_total),'model':MODELS[STYLE_MAP[s]['model_variant']]['name']} for s in order]}


class Producer:
    def __init__(self):
        self.stop=threading.Event(); self.process=None; self.cooldown=0; self.paused_styles=set()
        self.thread=threading.Thread(target=self.loop,daemon=True)
    def start(self):self.thread.start()
    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None:self.process.terminate()
        self.thread.join(timeout=5)
    def invoke(self,script,request_path,log_path,timeout=1800):
        with log_path.open('ab') as log:
            python=SA3_PYTHON if script=='generate_sa3_worker.py' else PYTHON
            self.process=subprocess.Popen([str(python),'-u',str(PROJECT/'scripts'/script),str(request_path)],cwd=PROJECT,env={**os.environ,'AMBIENT_PARENT_PID':str(os.getpid())},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:return self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(); raise RuntimeError(f'worker_timeout: {script}')
            finally:self.process=None
    def process_job(self,job):
        try:
            with InferenceLease():
                if migration.active:return
                return self._process_job(job)
        except BlockingIOError:return
    def _process_job(self,job):
        if job['style'] not in STYLE_MAP:return self.fail(job,'style_retired','This music category is no longer available')
        id=job['id']; p=json.loads(job['params']); work=DATA/'staging'/id
        work.mkdir(parents=True,exist_ok=True)
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            busy=db.execute("SELECT id FROM jobs WHERE status IN ('running','processing') AND id<>?",(id,)).fetchone()
            current=db.execute('SELECT status FROM jobs WHERE id=?',(id,)).fetchone()
            if busy or not current or current['status']!='queued':return
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1,error_code=NULL,error=NULL,updated=? WHERE id=?",(now(),id))
        if min(shutil.disk_usage(DATA).free,shutil.disk_usage(library_root()).free)<settings()['minimum_free_gb']*1e9:
            return self.fail(job,'filesystem_error','Staging or library disk reserve is insufficient; playback remains available')
        variant=p.get('model_variant','acestep-v15-turbo')
        if variant not in MODELS:return self.fail(job,'model_load_error','Unknown model variant')
        sa3=variant=='stable-audio-3-medium'
        model_root=configured_model_root('stable-audio-3-medium' if sa3 else 'ace-step')
        if sa3:
            required=[SA3_PYTHON]+[model_root/name for name in ['model_config.json','model.safetensors','t5gemma-b-b-ul2/model.safetensors','t5gemma-b-b-ul2/tokenizer.json']]
        else:
            required=[model_root/'checkpoints'/name for name in [variant+'/model.safetensors','Qwen3-Embedding-0.6B/model.safetensors','vae/diffusion_pytorch_model.safetensors']]
            if p.get('lm_enabled'):required.append(model_root/'checkpoints/acestep-5Hz-lm-0.6B/model.safetensors')
        required.append(configured_model_root('clap')/'pytorch_model.bin')
        missing=[str(p) for p in required if not p.exists()]
        if missing:return self.fail(job,'model_load_error','Required local weights missing: '+', '.join(missing))
        p.update(output=str(work),model_root=str(model_root))
        event('generation_started',f'{STYLE_MAP[job["style"]]["name"]} · {p["duration"]} 秒',id)
        with (DATA/'.log'/f'{id}.log').open('a',encoding='utf8') as log:
            log.write(json.dumps({'event':'generation_started','job_id':id,'style':job['style'],'model_variant':variant,'model':MODELS[variant]['name'],'duration':p['duration']},ensure_ascii=False)+'\n')
        req=work/'request.json'; req.write_text(json.dumps(p),encoding='utf8')
        # A restart/retry must never treat an earlier worker's result as fresh output.
        for name in ('result.json','qc-result.json'):(work/name).unlink(missing_ok=True)
        code=self.invoke('generate_sa3_worker.py' if sa3 else 'generate_worker.py',req,DATA/'.log'/f'{id}.log',7200 if sa3 else 1800)
        if not (work/'result.json').exists():return self.fail(job,'generation_error',f'Inference worker exited {code} without result')
        result=json.loads((work/'result.json').read_text(encoding='utf8'))
        if not result['success']:return self.fail(job,result['error_code'],result['error'])
        p.update(source=result['path'],duration=result.get('duration_requested',p['duration'])); req.write_text(json.dumps(p),encoding='utf8')
        with connection() as db:db.execute("UPDATE jobs SET status='processing',updated=? WHERE id=?",(now(),id))
        event('audio_processing_started','响度、完整性与重复度检查',id)
        code=self.invoke('qc_worker.py',req,DATA/'.log'/f'{id}.log',900)
        if not (work/'qc-result.json').exists():return self.fail(job,'audio_processing_error',f'QC worker exited {code} without result')
        qc=json.loads((work/'qc-result.json').read_text(encoding='utf8'))
        if not qc['success']:return self.fail(job,qc['error_code'],qc['error'])
        self.promote(job,p,result,qc,work)
    @exclusive
    def promote(self,job,p,result,qc,work):
        id=job['id']; archive_file=qc.get('archive_file','normalized.opus')
        if archive_file not in ('normalized.opus','normalized.flac'):return self.fail(job,'audio_processing_error','Invalid archive filename')
        source=work/archive_file
        with source.open('rb') as f:actual_hash=hashlib.file_digest(f,'sha256').hexdigest()
        if actual_hash!=qc['qc']['final']['sha256']:
            return self.fail(job,'qc_rejection','archive_checksum_mismatch: output changed after QC')
        vector=np.fromfile(work/'embedding.bin','<f4'); fingerprint=np.fromfile(work/'fingerprint.bin','<f4').reshape(12,64)
        exact=bool(rows("SELECT id FROM tracks WHERE json_extract(metadata,'$.qc.final.sha256')=? LIMIT 1",(qc['qc']['final']['sha256'],)))
        with connection() as db:
            candidates=db.execute("SELECT id,embedding,fingerprint FROM tracks WHERE status IN ('ready','retiring') OR id IN (SELECT id FROM tracks ORDER BY created DESC LIMIT 10000)")
            duplicate,nearest=compare(vector,fingerprint,candidates)
        if exact or duplicate:return self.fail(job,'qc_rejection',f'duplicate_audio: {nearest}')
        cfg=settings(); used=rows("SELECT COALESCE(SUM(bytes),0) AS bytes FROM tracks WHERE status IN ('ready','retiring','review')")[0]['bytes']
        if used+source.stat().st_size+100000>cfg['capacity_gb']*1e9:
            return self.fail(job,'filesystem_error','shared_pool_capacity_reached')
        dest=library_root()/p['style']/f'{id}{source.suffix}'; dest.parent.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(dest.parent).free<source.stat().st_size+cfg['minimum_free_gb']*1e9:
            return self.fail(job,'filesystem_error','Library disk reserve is insufficient')
        title=f'{STYLE_MAP[p["style"]]["name"]} · {p["seed"]%10000:04d}'
        meta=dict(id=id,title=title,created=now(),play_count=0,style=p['style'],
            model=result['model'],seed=p['seed'],bpm_requested=p['bpm'],key_requested=p['key'],timesignature_requested=p.get('timesignature','4'),
            key_measured=None,key_note='conditioning value; heuristic estimate is in analysis.tonality, not a verified transcription',
            tonal_policy=p.get('tonal_policy'),
            instruments=STYLE_MAP[p['style']]['instruments'],moods=STYLE_MAP[p['style']]['moods'],
            instruments_note='Requested arrangement; not a source-separated instrument verification',
            keywords=STYLE_MAP[p['style']]['subtitle'],prompt=p['prompt'],prompt_revision=p.get('prompt_revision','2026-09-24-initial'),duration=qc['qc']['final']['duration'],
            generation=result,qc=qc['qc'],analysis=qc['analysis'],nearest=nearest,
            style_review=STYLE_MAP[p['style']].get('style_review','prompt conditioned; human listening acceptance pending'),similarity_scope='all active tracks plus most recent 10000 accepted tracks including retired history')
        safe_path(dest); meta['status']='ready'
        encoded=json.dumps(meta,ensure_ascii=False,indent=2)
        staged_meta=work/'metadata.json'; staged_meta.write_text(encoded,encoding='utf8')
        size=source.stat().st_size+len(encoded.encode('utf8'))
        published=[]
        try:
            with connection() as db:
                # Reserve the unique ID before touching the destination. A second
                # publisher cannot overwrite already accepted audio and then fail INSERT.
                db.execute('INSERT INTO tracks(id,style,title,path,duration,bytes,created,metadata,embedding,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?)',(id,p['style'],title,str(dest),meta['duration'],size,now(),encoded,vector.tobytes(),fingerprint.tobytes()))
                # Music may be on another drive; stage the copy on that drive
                # before the atomic rename, rather than cross-volume replace().
                temporary=dest.with_suffix(dest.suffix+'.part')
                try:
                    with source.open('rb') as inp,temporary.open('wb') as out:
                        shutil.copyfileobj(inp,out);out.flush();os.fsync(out.fileno())
                    with temporary.open('rb') as check:
                        if hashlib.file_digest(check,'sha256').hexdigest()!=actual_hash:raise OSError('Destination copy checksum mismatch')
                    temporary.replace(dest);published.append(dest)
                finally:temporary.unlink(missing_ok=True)
                meta_dest=dest.with_suffix('.json');meta_tmp=meta_dest.with_suffix('.json.part')
                try:shutil.copyfile(staged_meta,meta_tmp);meta_tmp.replace(meta_dest);published.append(meta_dest)
                finally:meta_tmp.unlink(missing_ok=True)
                db.execute("UPDATE jobs SET status='done',updated=?,track_id=?,error_code=NULL,error=NULL WHERE id=?",(now(),id,id))
        except Exception:
            if not rows('SELECT id FROM tracks WHERE id=?',(id,)):
                for path in published:path.unlink(missing_ok=True)
            raise
        event('track_accepted',f'{title}; {meta["qc"]["final"]["lufs"]} LUFS',id)
    def fail(self,job,code,message):
        retry=code=='cuda_oom' and job['attempts']<1
        p=json.loads(job['params'])
        if retry:p['duration']=max(30,p['duration']//2)
        with connection() as db:
            db.execute('UPDATE jobs SET status=?,error_code=?,error=?,updated=?,params=?,available_at=? WHERE id=?',('queued' if retry else 'failed',code,message[:4000],now(),json.dumps(p),time.time()+60,job['id']))
        event(code,message[:2000],job['id'],'warning' if code=='qc_rejection' else 'error')
        if code=='model_load_error':self.cooldown=time.time()+300
    def cleanup(self):
        # Only completed job staging directories owned by this database are removable.
        for row in rows("SELECT id FROM jobs WHERE status IN ('done','failed') ORDER BY created DESC"):
            p=safe_path(DATA/'staging'/row['id'],'staging')
            if p.exists():shutil.rmtree(p)
        logs=sorted((p for p in (DATA/'.log').glob('*.log') if len(p.stem)==32 and all(c in '0123456789abcdef' for c in p.stem)),key=lambda p:p.stat().st_mtime,reverse=True)
        for p in logs[100:]:p.unlink(missing_ok=True)
    def refill(self):
        if migration.active:return
        from .preferences import read_config
        from .provisioning import snapshot
        if not read_config().get('setup',{}).get('complete',True) or snapshot()['active']:return
        cfg=settings()
        if not cfg['auto_generate']:return
        if min(shutil.disk_usage(DATA).free,shutil.disk_usage(library_root()).free)<cfg['minimum_free_gb']*1e9:return
        if rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"):return
        pool=rows("SELECT style,COUNT(*) count FROM tracks WHERE status='ready' GROUP BY style")
        counts={r['style']:r['count'] for r in pool}
        archive=rows("SELECT COALESCE(SUM(bytes),0) AS bytes FROM tracks WHERE status IN ('ready','retiring','review')")[0]['bytes']
        # A three-minute 24-bit stereo FLAC can approach 52 MB before metadata.
        if archive>=cfg['capacity_gb']*1e9-64_000_000:return
        paused={s for s in cfg['enabled_styles'] if style_retry_after(s)>time.time()}
        for style in paused-self.paused_styles:event('style_cooldown',f'{STYLE_MAP[style]["name"]}: three consecutive rejected/failed trials; automatic refill waits 30 minutes, other styles continue',level='warning')
        self.paused_styles=paused
        choice=refill_style(counts,[s for s in cfg['enabled_styles'] if s not in paused],cfg['style_weights'])
        if choice:enqueue(choice)
    def loop(self):
        with gate:
            if not migration.active:maintenance()
        while not self.stop.is_set():
            try:
                if migration.active:self.stop.wait(.5);continue
                if time.time()<self.cooldown:self.stop.wait(5);continue
                self.refill()
                jobs=rows("SELECT * FROM jobs WHERE status='queued' AND available_at<=? ORDER BY created LIMIT 1",(time.time(),))
                if jobs:
                    try:self.process_job(jobs[0])
                    except OSError as exc:self.fail(jobs[0],'filesystem_error',str(exc))
                    except Exception as exc:self.fail(jobs[0],'generation_error',str(exc))
                    with gate:
                        if not migration.active:self.cleanup();maintenance()
            except Exception as exc:
                try:event('filesystem_error',str(exc),level='error')
                except Exception:pass
            self.stop.wait(settings()['generation_interval'])
