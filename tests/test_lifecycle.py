"""Regression tests use isolated temp data, never delete the real generated collection."""
import importlib
import hashlib
import sqlite3
import json
import sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest


@pytest.fixture
def system(tmp_path,monkeypatch):
    monkeypatch.setenv('AMBIENT_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('AMBIENT_NO_WORKER','1')
    monkeypatch.setenv('AMBIENT_API_TOKEN','test-token-not-a-secret')
    for m in list(sys.modules):
        if m=='server' or m.startswith('server.'):del sys.modules[m]
    database,library,queue,config=[importlib.import_module('server.'+name) for name in ['database','library','queue','config']]
    database.initialize()
    # These tests exercise an already-onboarded collection. Fresh startup is
    # tested separately in test_settings_v11.py.
    from server.preferences import read_config,write_config,save_settings
    user=read_config();user['setup'].update(complete=True,legacy_adopted=True);write_config(user)
    save_settings({'auto_generate':True})
    return database,library,queue,config


def add_track(system,id='a'*32,style='lofi',duration=60,plays=0):
    db,lib,q,cfg=system
    path=cfg.DATA/'MusicLib'/style/(id+'.opus');path.parent.mkdir(exist_ok=True);path.write_bytes(b'fixture')
    meta={'qc':{'final':{'sha256':id,'lufs':-18}}}
    with db.connection() as c:
        c.execute('INSERT INTO tracks(id,style,title,path,duration,bytes,plays,created,metadata) VALUES(?,?,?,?,?,?,?,?,?)',(id,style,'fixture',str(path),duration,7,plays,db.now(),json.dumps(meta)))
    lib.write_sidecar(id)
    return path


def full_play(lib,id):
    with patch('server.library.time.time',return_value=100):sid=lib.start_play(id)
    for t in range(105,161,5):
        with patch('server.library.time.time',return_value=t):lib.ping_play(sid)
    with patch('server.library.time.time',return_value=160):result=lib.ping_play(sid,finish=True)
    return sid,result


def test_weighted_refill_converges_by_counts_and_respects_disabled(system):
    _,_,queue,config=system
    enabled=list(config.STYLE_MAP);sizes={s:0 for s in enabled}
    assert config.STYLE_MAP['lofi']['weight']+config.STYLE_MAP['ambient']['weight']==60
    for i in range(10000):
        selected=queue.refill_style(sizes,enabled)
        sizes[selected]+=1
    total=sum(sizes.values())
    for s in enabled:assert abs(sizes[s]/total-config.STYLE_MAP[s]['weight']/100)<.001
    assert queue.refill_style(sizes,['ambient'])=='ambient'
    assert queue.refill_style(sizes,[]) is None


def test_every_new_style_requests_major(system):
    db,_,queue,cfg=system
    for style in cfg.STYLE_MAP:
        id=queue.enqueue(style,180)
        p=json.loads(db.rows('SELECT params FROM jobs WHERE id=?',(id,))[0]['params'])
        if style=='guzheng':
            assert p['tonal_policy']=='gong-pentatonic-prompt-only'
            assert p['bpm'] is None and p['timesignature']=='free'
            assert p['prompt'] in cfg.STYLE_MAP[style]['prompts']
            assert p['model_variant']=='stable-audio-3-medium'
            continue
        assert p['key'].endswith(' Major') and p['key'] in p['prompt']
        assert p['tonal_policy']=='major-v6'


def test_repeated_style_rejection_cannot_starve_other_styles(system):
    db,_,queue,_=system
    for i in range(3):
        id=queue.enqueue('guitar')
        with db.connection() as c:c.execute("UPDATE jobs SET status='failed',error_code='qc_rejection' WHERE id=?",(id,))
    assert queue.style_retry_after('guitar')>queue.time.time()
    assert queue.style_retry_after('lofi')==0
    producer=queue.Producer()
    with patch('server.queue.shutil.disk_usage') as usage:
        usage.return_value.free=100e9
        producer.refill()
    job=db.rows("SELECT style FROM jobs WHERE status='queued'")[0]
    assert job['style']!='guitar'
    # A successful manual trial restores automatic eligibility immediately.
    id=queue.enqueue('guitar')
    with db.connection() as c:c.execute("UPDATE jobs SET status='done' WHERE id=?",(id,))
    assert queue.style_retry_after('guitar')==0


def test_sa3_specialist_recipes_keep_major_tempo_and_independent_backends(system):
    db,_,queue,cfg=system
    for style in ['daily_piano','orchestral','guitar','artcore']:
        id=queue.enqueue(style,180)
        p=json.loads(db.rows('SELECT params FROM jobs WHERE id=?',(id,))[0]['params'])
        assert p['model_variant']=='stable-audio-3-medium'
        assert p['key'].endswith(' Major') and p['key'] in p['prompt']
        assert f'{p["bpm"]} BPM' in p['prompt'] and '{bpm}' not in p['prompt']
        assert p['prompt'].startswith('TrackType: Instrument' if style in ('guitar','daily_piano') else 'TrackType: Music')
        assert p['duration']==180 and not p['lm_enabled']
    assert cfg.STYLE_MAP['lofi']['model_variant']=='acestep-v15-turbo'
    assert cfg.STYLE_MAP['ambient']['model_variant']=='stable-audio-3-medium'
    assert cfg.STYLE_MAP['anime_daily']['model_variant']=='acestep-v15-sft'


def test_recipe_change_releases_cooldown_and_preserves_historical_log_model(system):
    db,_,queue,cfg=system
    for _ in range(3):
        id=queue.enqueue('guitar')
        with db.connection() as c:
            c.execute("UPDATE jobs SET status='failed',error_code='qc_rejection' WHERE id=?",(id,))
    assert queue.style_retry_after('guitar')>queue.time.time()
    cfg.STYLE_MAP['guitar']['prompt_revision']='next-recipe'
    assert queue.style_retry_after('guitar')==0
    with db.connection() as c:
        c.execute("UPDATE jobs SET params=json_set(params,'$.model_variant','acestep-v15-sft') WHERE id=?",(id,))
        c.execute("INSERT INTO events(time,level,code,job_id,detail) VALUES(?,?,?,?,?)",(db.now(),'info','legacy',id,'before migration'))
    db.initialize()
    historical=db.rows("SELECT model_variant,model_name FROM events WHERE code='legacy'")[0]
    assert historical=={'model_variant':'acestep-v15-sft','model_name':'ACE-Step 1.5 SFT'}
    new=queue.enqueue('guitar');db.event('generation_started','test',new)
    current=db.rows("SELECT model_variant,model_name FROM events WHERE code='generation_started'")[0]
    assert current=={'model_variant':'stable-audio-3-medium','model_name':'Stable Audio 3 Medium'}


def test_refill_plan_matches_producer_and_exposes_underrepresented_style(system):
    db,_,queue,cfg=system
    sizes={s:spec['weight'] for s,spec in cfg.STYLE_MAP.items()}
    sizes['daily_piano']=1
    for i,(style,count) in enumerate(sizes.items()):
        for j in range(count):
            id=f'{i*100+j:032x}';add_track(system,id,style)
            with db.connection() as c:c.execute('UPDATE tracks SET bytes=? WHERE id=?',((i+1)*10_000_000,id))
    plan=queue.refill_plan();first=plan['priority'][0]
    assert first['style']==queue.refill_style(sizes,list(sizes))=='daily_piano'
    assert first['target_percent']==10 and first['current_percent']<2
    assert first['model']=='Stable Audio 3 Medium' and plan['basis']=='tracks'
    with db.connection() as c:c.execute('UPDATE tracks SET bytes=bytes*20')
    assert queue.refill_plan()==plan
    with db.connection() as c:c.execute("UPDATE settings SET value='[]' WHERE key='enabled_styles'")
    assert queue.refill_plan()['priority']==[]


def test_four_complete_plays_retire_and_delete(system):
    db,lib,_,_=system;p=add_track(system)
    for i in range(4):
        _,result=full_play(lib,'a'*32)
        assert result['counted']
        assert p.exists()==(i<3)
    assert db.rows('SELECT status,plays FROM tracks')[0]=={'status':'retired','plays':4}
    assert not p.with_suffix('.json').exists()


def test_duplicate_finish_and_short_skip_never_double_count(system):
    db,lib,_,_=system;add_track(system)
    sid,result=full_play(lib,'a'*32)
    assert lib.ping_play(sid,finish=True)=={'counted':False}
    with patch('server.library.time.time',return_value=200):sid=lib.start_play('a'*32)
    with patch('server.library.time.time',return_value=260):r=lib.ping_play(sid,finish=True,reason='skip')
    assert not r['counted'] and r['listened']==8
    assert db.rows('SELECT plays FROM tracks')[0]['plays']==1
    assert lib.tracks()[0]['metadata']['play_count']==1


def test_paused_and_crashed_session_cannot_count_wall_clock(system):
    db,lib,_,_=system;add_track(system)
    with patch('server.library.time.time',return_value=100):sid=lib.start_play('a'*32)
    with patch('server.library.time.time',return_value=10000):lib.ping_play(sid,playing=False)
    with patch('server.library.time.time',return_value=10001):r=lib.ping_play(sid,finish=True)
    assert r['listened']==1 and not r['counted']


def test_path_escape_cannot_delete_outside_owned_root(system,tmp_path):
    db,lib,_,cfg=system;p=add_track(system)
    outsider=tmp_path/'important.txt';outsider.write_text('keep')
    with db.connection() as c:c.execute('UPDATE tracks SET path=?',(str(outsider),))
    with pytest.raises(ValueError):lib.retire('a'*32)
    assert outsider.read_text()=='keep'


def test_missing_file_and_failed_deletion_recover(system):
    db,lib,_,_=system;p=add_track(system)
    with patch.object(Path,'unlink',side_effect=PermissionError('locked')):assert not lib.retire('a'*32)
    assert db.rows('SELECT status FROM tracks')[0]['status']=='retiring'
    lib.maintenance();assert not p.exists()
    p=add_track(system,'b'*32);p.unlink();lib.maintenance()
    assert db.rows("SELECT status FROM tracks WHERE id=?",('b'*32,))[0]['status']=='missing'


def test_shuffle_avoids_history_and_excludes_current(system):
    db,lib,_,_=system
    for x in 'abcdef':add_track(system,x*32)
    seen=[]
    for i in range(6):
        track=lib.choose('lofi',seen[-1] if seen else None);seen.append(track['id']);lib.start_play(track['id'])
    assert len(set(seen))==6
    assert lib.choose('lofi',seen[-1])['id']!=seen[-1]
    assert lib.choose('guitar') is None


def test_oom_requeues_shorter_once_and_qc_rejection_continues(system):
    db,_,q,_=system;id=q.enqueue('lofi',120);job=db.rows('SELECT * FROM jobs')[0];p=q.Producer()
    p.fail(job,'cuda_oom','injected allocation failure')
    row=db.rows('SELECT * FROM jobs')[0]
    assert row['status']=='queued' and json.loads(row['params'])['duration']==60
    row['attempts']=1;p.fail(row,'cuda_oom','again')
    assert db.rows('SELECT status FROM jobs')[0]['status']=='failed'
    second=q.enqueue('lofi',60);job=db.rows('SELECT * FROM jobs WHERE id=?',(second,))[0]
    p.fail(job,'qc_rejection','silent')
    assert q.enqueue('ambient',60)


def test_restart_recovers_interrupted_jobs(system):
    db,_,q,_=system;id=q.enqueue()
    with db.connection() as c:c.execute("UPDATE jobs SET status='processing'")
    db.initialize();row=db.rows('SELECT * FROM jobs')[0]
    assert row['status']=='queued' and row['error_code']=='interrupted'


def test_live_inference_lease_prevents_restart_stealing_job(system):
    db,_,q,_=system;id=q.enqueue()
    from server.locks import InferenceLease
    with db.connection() as c:c.execute("UPDATE jobs SET status='running'")
    with InferenceLease():
        with pytest.raises(BlockingIOError):
            with InferenceLease():pass
        db.initialize()
        assert db.rows('SELECT status FROM jobs')[0]['status']=='running'
    db.initialize()
    assert db.rows('SELECT status FROM jobs')[0]['status']=='queued'


def test_crashed_retry_cannot_reuse_stale_worker_success(system):
    db,_,q,cfg=system;id=q.enqueue();job=db.rows('SELECT * FROM jobs')[0]
    work=cfg.DATA/'staging'/id;work.mkdir()
    (work/'result.json').write_text(json.dumps({'success':True,'path':'obsolete.wav'}))
    (work/'qc-result.json').write_text(json.dumps({'success':True}))
    variant=json.loads(job['params'])['model_variant']
    paths=[f'models/ace-step/checkpoints/{variant}/model.safetensors',
           'models/ace-step/checkpoints/Qwen3-Embedding-0.6B/model.safetensors',
           'models/ace-step/checkpoints/vae/diffusion_pytorch_model.safetensors',
           'models/clap/pytorch_model.bin']
    for name in paths:
        p=cfg.DATA/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    producer=q.Producer()
    with patch.object(producer,'invoke',return_value=1):producer.process_job(job)
    result=db.rows('SELECT * FROM jobs')[0]
    assert result['status']=='failed' and result['error_code']=='generation_error'
    assert 'without result' in result['error']
    assert not (work/'qc-result.json').exists()


def test_sa3_dispatch_keeps_free_rhythm_and_actual_fallback_duration(system):
    db,_,q,cfg=system
    id=q.enqueue('guzheng',180);job=db.rows('SELECT * FROM jobs')[0]
    for name in ['model_config.json','model.safetensors','t5gemma-b-b-ul2/model.safetensors','t5gemma-b-b-ul2/tokenizer.json']:
        p=cfg.DATA/'models/stable-audio-3-medium'/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    clap=cfg.DATA/'models/clap/pytorch_model.bin';clap.parent.mkdir(parents=True);clap.touch()
    calls=[]
    def invoke(script,req,log,timeout=1800):
        params=json.loads(req.read_text());calls.append(script)
        if script=='generate_sa3_worker.py':
            assert params['bpm'] is None and params['timesignature']=='free'
            assert Path(params['model_root']).name=='stable-audio-3-medium'
            (req.parent/'result.json').write_text(json.dumps({'success':True,'path':'fixture.wav','duration_requested':120}))
        else:
            assert script=='qc_worker.py' and params['duration']==120
            (req.parent/'qc-result.json').write_text(json.dumps({'success':False,'error_code':'qc_rejection','error':'fixture rejection'}))
        return 0
    producer=q.Producer()
    with patch.object(q,'SA3_PYTHON',Path(sys.executable)),patch.object(producer,'invoke',side_effect=invoke):producer.process_job(job)
    assert calls==['generate_sa3_worker.py','qc_worker.py']
    assert db.rows('SELECT error_code FROM jobs')[0]['error_code']=='qc_rejection'


def test_changed_audio_after_qc_cannot_be_published(system):
    db,_,q,cfg=system;id=q.enqueue();job=db.rows('SELECT * FROM jobs')[0]
    work=cfg.DATA/'staging'/id;work.mkdir();(work/'normalized.opus').write_bytes(b'changed after measurement')
    q.Producer().promote(job,{}, {},{'qc':{'final':{'sha256':'old hash'}}},work)
    assert db.rows('SELECT status,error_code FROM jobs')[0]=={'status':'failed','error_code':'qc_rejection'}
    assert not db.rows('SELECT id FROM tracks')


def test_duplicate_publisher_cannot_overwrite_accepted_media(system):
    db,_,q,cfg=system;id=q.enqueue();job=db.rows('SELECT * FROM jobs')[0];original=add_track(system,id)
    work=cfg.DATA/'staging'/id;work.mkdir();source=work/'normalized.opus';source.write_bytes(b'new candidate')
    np.zeros(512,dtype='<f4').tofile(work/'embedding.bin');np.zeros((12,64),dtype='<f4').tofile(work/'fingerprint.bin')
    qc={'qc':{'final':{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'duration':60,'lufs':-18}},'analysis':{}}
    with pytest.raises(sqlite3.IntegrityError):q.Producer().promote(job,json.loads(job['params']),{'model':'fixture'},qc,work)
    assert original.read_bytes()==b'fixture'
    assert source.read_bytes()==b'new candidate'


def test_shared_capacity_and_disabled_refill(system):
    db,_,q,_=system;add_track(system);add_track(system,'b'*32,'ambient')
    with db.connection() as c:
        c.execute("UPDATE tracks SET bytes=80000000000")
        c.execute("UPDATE settings SET value=? WHERE key='enabled_styles'",(json.dumps(['lofi','ambient']),))
    p=q.Producer();p.refill();assert not db.rows('SELECT * FROM jobs')
    with db.connection() as c:
        c.execute('UPDATE tracks SET bytes=7')
        c.execute("UPDATE settings SET value='false' WHERE key='auto_generate'")
    p.refill();assert not db.rows('SELECT * FROM jobs')


def test_api_requires_token_and_validates_mutations(system,monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import app
    from server import provisioning
    monkeypatch.setattr(provisioning,'model_status',lambda:[{'id':'acestep-v15-turbo','installed':True,'eligible':True}])
    with TestClient(app) as client:
        assert client.get('/state').status_code==401
        client.headers['x-ambient-token']='test-token-not-a-secret'
        assert client.get('/health').json()['ok']
        assert client.post('/jobs',json={'style':'lofi','duration':9999}).status_code==422
        assert client.patch('/settings',json={'data_root':'C:/'}).status_code==422
        assert client.patch('/settings',json={'enabled_styles':['unknown']}).status_code==400
        assert client.get('/audio/does-not-exist').status_code==404
        assert client.post('/jobs',json={'style':'lofi','duration':60}).status_code==200
        assert client.patch('/settings',json={'duration':180}).status_code==200
        created=client.post('/jobs',json={'style':'lofi'}).json()['ids'][0]
        assert json.loads(system[0].rows('SELECT params FROM jobs WHERE id=?',(created,))[0]['params'])['duration']==180


def test_embedding_duplicate_needs_both_semantic_and_acoustic_agreement():
    from server.embedding import compare
    vector=np.zeros(512,dtype='<f4');vector[0]=1
    fingerprint=(np.ones((12,64))/np.sqrt(12)).astype('<f4')
    candidate=dict(id='same',embedding=vector.tobytes(),fingerprint=fingerprint.tobytes())
    assert compare(vector,fingerprint,[candidate])[0]
    other=np.zeros((12,64),dtype='<f4');other[0]=1
    assert not compare(vector,other,[candidate])[0]


def test_review_audio_is_excluded_but_counts_towards_capacity(system):
    db,lib,q,cfg=system;path=add_track(system,style='guitar')
    with db.connection() as c:c.execute("UPDATE tracks SET status='review',bytes=10000000000")
    assert lib.choose() is None
    assert lib.tracks()==[]
    q.Producer().refill()
    assert not db.rows('SELECT * FROM jobs')
    assert path.exists()
    from server.app import state
    assert state()['archive']=={'bytes':10000000000,'review_count':1}


def test_merged_preferences_preserve_disabled_styles_and_cancel_old_jobs(system):
    db,_,q,_=system
    from server.preferences import save_settings
    save_settings({'enabled_styles':['bright_piano','hybrid','daily_piano']})
    id=q.enqueue()
    with db.connection() as c:c.execute("UPDATE jobs SET style='bright_piano',status='running' WHERE id=?",(id,))
    db.initialize()
    assert db.settings()['enabled_styles']==['daily_piano','orchestral']
    assert db.rows('SELECT status,error_code FROM jobs')[0]=={'status':'cancelled','error_code':'style_retired'}


def test_flac_promotion_keeps_extension_and_api_type(system):
    db,_,q,cfg=system;id=q.enqueue('guitar');job=db.rows('SELECT * FROM jobs')[0]
    params=json.loads(job['params']);params['encoding']={'codec':'flac','preserve_dynamics':True};job['params']=json.dumps(params)
    work=cfg.DATA/'staging'/id;work.mkdir();source=work/'normalized.flac';source.write_bytes(b'flac fixture')
    np.zeros(512,dtype='<f4').tofile(work/'embedding.bin');np.zeros((12,64),dtype='<f4').tofile(work/'fingerprint.bin')
    qc={'archive_file':'normalized.flac','qc':{'final':{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'duration':180,'lufs':-18}},'analysis':{}}
    q.Producer().promote(job,json.loads(job['params']),{'model':'fixture'},qc,work)
    track=db.rows('SELECT path FROM tracks')[0]
    assert Path(track['path']).suffix=='.flac'
    from server.app import audio
    assert audio(id).media_type=='audio/flac'
    assert json.loads(job['params'])['encoding']['codec']=='flac'


def test_selected_sft_missing_does_not_silently_use_turbo(system):
    db,_,q,cfg=system
    id=q.enqueue('daily_piano');job=db.rows('SELECT * FROM jobs')[0]
    params=json.loads(job['params']);params.update(model_variant='acestep-v15-sft',lm_enabled=False)
    with db.connection() as c:c.execute('UPDATE jobs SET params=? WHERE id=?',(json.dumps(params),id))
    for name in ['acestep-v15-turbo/model.safetensors','Qwen3-Embedding-0.6B/model.safetensors','vae/diffusion_pytorch_model.safetensors']:
        p=cfg.DATA/'models/ace-step/checkpoints'/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    p=cfg.DATA/'models/clap/pytorch_model.bin';p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    producer=q.Producer()
    with patch.object(producer,'invoke') as invoke:producer.process_job(db.rows('SELECT * FROM jobs')[0])
    invoke.assert_not_called()
    failure=db.rows('SELECT status,error_code,error FROM jobs')[0]
    assert failure['status']=='failed' and failure['error_code']=='model_load_error'
    assert 'acestep-v15-sft' in failure['error']
