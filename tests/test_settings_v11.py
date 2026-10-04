import importlib,json,sys,hashlib,time
from pathlib import Path
import pytest

@pytest.fixture
def system(tmp_path,monkeypatch):
    monkeypatch.setenv('AMBIENT_DATA_DIR',str(tmp_path));monkeypatch.setenv('AMBIENT_NO_WORKER','1')
    for name in list(sys.modules):
        if name=='server' or name.startswith('server.'):del sys.modules[name]
    db=importlib.import_module('server.database');db.initialize()
    prefs=importlib.import_module('server.preferences');provision=importlib.import_module('server.provisioning')
    return db,prefs,provision,tmp_path

def test_consent_and_first_track_gate(system,monkeypatch):
    db,prefs,p,root=system
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**k:pytest.fail('must not scan without consent'))
    with pytest.raises(ValueError):p.scan_device(False)
    from fastapi.testclient import TestClient
    from server.app import app,TOKEN
    with TestClient(app) as c:
        assert c.get('/setup').status_code==401
        headers={'x-ambient-token':TOKEN}
        assert c.get('/setup',headers=headers).json()['setup']['complete'] is False
        for url in ['/next','/audio/abc']:
            assert c.get(url,headers=headers).status_code==423
        assert c.post('/jobs',headers=headers,json={'style':'lofi'}).status_code==423

def test_device_floor_is_explicit(system):
    p=system[2]
    assert not p.evaluate_device(32,3)['ace']
    assert p.evaluate_device(16,4)['ace'] and not p.evaluate_device(16,4)['sa3']
    assert p.evaluate_device(24,6)['sa3']
    assert not p.evaluate_device(64,24,False)['sa3']

def test_config_roundtrip_and_legacy_adoption(system):
    db,prefs,p,root=system
    prefs.save_settings({'duration':150,'auto_generate':False,'style_weights':{'lofi':100}})
    assert json.loads((root/'config.json').read_text(encoding='utf8'))['settings']['duration']==150
    config=prefs.read_config();config['settings']['duration']=120;prefs.write_config(config);db.initialize()
    assert db.settings()['duration']==120
    with db.connection() as con:con.execute("INSERT INTO tracks(id,style,title,path,duration,bytes,created,metadata) VALUES(?,?,?,?,?,?,?,?)",('a'*32,'lofi','old',str(root/'old.opus'),180,100,db.now(),'{}'))
    (root/'config.json').unlink();db.initialize()
    assert prefs.read_config()['setup']['complete'] and prefs.read_config()['setup']['legacy_adopted']
    assert db.settings()['auto_generate'] is False

def test_recipe_validation_and_actual_job_snapshot(system):
    db,prefs,p,root=system
    from server.config import STYLES
    styles=json.loads(json.dumps(STYLES));styles[0]['bpm']=[90,70]
    with pytest.raises(ValueError):prefs.replace_styles(styles)
    styles[0]['bpm']=[70,74];styles[0]['name']='A <tag> test';styles[0]['prompts']=['Gentle instrumental cafe music.']
    prefs.replace_styles(styles)
    from server.queue import enqueue
    job=enqueue('lofi',150);params=json.loads(db.rows('SELECT params FROM jobs WHERE id=?',(job,))[0]['params'])
    assert 70<=params['bpm']<=74 and 'Gentle instrumental' in params['prompt']
    assert params['prompt_revision'].startswith('user-')

def test_cloud_path_switch_only_after_success(system,monkeypatch):
    db,prefs,p,root=system
    cfg=prefs.read_config();cfg['setup']['hardware']={'ace':True,'sa3':False};prefs.write_config(cfg)
    original=cfg['paths']['models'];target=root/'new-models'
    monkeypatch.setattr(p,'_manifest',lambda *a: (_ for _ in ()).throw(RuntimeError('contains-secret-should-not-appear')))
    p.start_download(['acestep-v15-turbo'],str(target),'example-credential')
    p._thread.join(5)
    assert p.snapshot()['phase']=='failed'
    assert 'secret' not in p.snapshot()['error'] and 'credential' not in json.dumps(prefs.read_config())
    assert prefs.read_config()['paths']['models']==original
    with pytest.raises(ValueError):p.start_download(['stable-audio-3-medium'],str(target))

def test_download_resume_and_checksum(system,monkeypatch):
    db,prefs,p,root=system
    payload=b'correct model bytes';sha=hashlib.sha256(payload).hexdigest();part=root/'weights.bin.part';part.write_bytes(payload[:5])
    import requests,huggingface_hub
    class Response:
        status_code=206;headers={'Content-Range':f'bytes 5-{len(payload)-1}/{len(payload)}'}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def raise_for_status(self):pass
        def iter_content(self,*a):yield payload[5:]
    def get(url,**kwargs):assert kwargs['headers']['Range']=='bytes=5-';return Response()
    monkeypatch.setattr(requests,'get',get)
    monkeypatch.setattr(p.shutil,'disk_usage',lambda _:type('Disk',(),{'free':100_000_000_000})())
    p._download([{'repo':'test/repo','revision':'abc','remote':'weights.bin','relative':'weights.bin','size':len(payload),'sha256':sha}],root,None)
    assert (root/'weights.bin').read_bytes()==payload and not part.exists()

def test_custom_image_is_separate_from_original(system):
    from PIL import Image
    from server.assets import import_asset,media_path
    db,prefs,p,root=system
    src=root/'original.png';Image.new('RGB',(100,80),'blue').save(src);before=src.read_bytes()
    row=import_asset('images',str(src),'A <script>','♪','forest','night',['ambient'],[.7,.4])
    assert src.read_bytes()==before and media_path('images',row['id']).suffix=='.webp'
    assert prefs.read_config()['images'][0]['focus']==[.7,.4]

def test_first_setup_cannot_choose_valley_without_sa3(system):
    db,prefs,p,root=system
    cfg=prefs.read_config();cfg['setup'].update(models_verified=True,models=['acestep-v15-turbo'],hardware={'ace':True,'sa3':False});prefs.write_config(cfg)
    with pytest.raises(ValueError,match='空谷听泉'):p.begin_first(str(root/'music'),{s:0 for s in ['lofi']},['guzheng'])

def test_missing_model_cannot_be_reenabled_after_setup(system,monkeypatch):
    db,prefs,p,root=system
    cfg=prefs.read_config();cfg['setup']['complete']=True;prefs.write_config(cfg)
    prefs.save_settings({'enabled_styles':['lofi']})
    monkeypatch.setattr(p,'model_status',lambda:[{'id':'acestep-v15-turbo','installed':True,'eligible':True},{'id':'stable-audio-3-medium','installed':False,'eligible':False}])
    from fastapi.testclient import TestClient
    from server.app import app,TOKEN
    with TestClient(app) as c:
        headers={'x-ambient-token':TOKEN}
        assert c.patch('/settings',headers=headers,json={'enabled_styles':['lofi','guzheng']}).status_code==400
        assert c.post('/jobs',headers=headers,json={'style':'guzheng'}).status_code==400
        assert db.settings()['enabled_styles']==['lofi']
        assert c.patch('/settings',headers=headers,json={'enabled_styles':[]}).status_code==200

def test_first_setup_saves_pins_and_queues_real_recipe(system,monkeypatch):
    db,prefs,p,root=system
    cfg=prefs.read_config();cfg['setup'].update(models_verified=True,models=['acestep-v15-turbo'],hardware={'ace':True,'sa3':False,'gpus':[{'vram_gb':4}]});prefs.write_config(cfg)
    monkeypatch.setattr(p,'model_status',lambda:[{'id':'acestep-v15-turbo','installed':True,'eligible':True}])
    monkeypatch.setattr(p.shutil,'disk_usage',lambda _:type('Disk',(),{'free':100_000_000_000})())
    from server.config import STYLE_MAP
    weights={s:100 if s=='lofi' else 0 for s in STYLE_MAP}
    status=p.begin_first(str(root/'first-library'),weights,['lofi'],['lofi'])
    assert status['first_job']['status']=='queued' and not status['setup']['complete']
    assert db.settings()['style_pins']==['lofi']
    assert db.settings()['enabled_styles']==['lofi']
    assert prefs.read_config()['settings']['style_pins']==['lofi']
    job=db.rows('SELECT params FROM jobs')[0]
    assert json.loads(job['params'])['model_variant']=='acestep-v15-turbo'
