"""The Save button is a single configuration transaction, not a series of autosaves."""
import copy
import pytest
from test_settings_v11 import system

@pytest.fixture
def client(system):
    from fastapi.testclient import TestClient
    from server.app import app,TOKEN
    with TestClient(app,headers={'x-ambient-token':TOKEN}) as c:yield c

def test_save_applies_all_tabs_and_updates_job_recipe(system,client):
    db,prefs,p,root=system
    r=client.get('/configuration').json();styles=copy.deepcopy(r['config']['styles'])
    styles[0]['bpm']=[71,74];styles[0]['prompts']=['Warm unhurried piano music.']
    result=client.put('/configuration/save',json={'revision':r['revision'],'settings':{'capacity_gb':30,'crossfade':8},'styles':styles,'paths':{'images':str(root/'chosen-images')}})
    assert result.status_code==200,result.text
    assert db.settings()['capacity_gb']==30 and db.settings()['crossfade']==8
    saved=prefs.read_config();assert saved['paths']['images']==str(root/'chosen-images')
    assert saved['styles'][0]['bpm']==[71,74] and saved['styles'][0]['prompt_revision'].startswith('user-')
    from server.queue import enqueue
    import json
    job=enqueue('lofi',150);params=json.loads(db.rows('SELECT params FROM jobs WHERE id=?',(job,))[0]['params'])
    assert 71<=params['bpm']<=74 and 'Warm unhurried' in params['prompt']

@pytest.mark.parametrize('invalid',[{'bpm':[90,70]},{'encoding':None},{'prompts':[]},{'id':None}])
def test_invalid_recipe_cannot_partially_commit_other_tabs(system,client,invalid):
    db,prefs,p,root=system
    before=prefs.read_config();r=client.get('/configuration').json();styles=copy.deepcopy(r['config']['styles']);styles[0].update(invalid)
    result=client.put('/configuration/save',json={'revision':r['revision'],'settings':{'capacity_gb':30},'styles':styles,'paths':{'images':str(root/'must-not-create')}})
    assert result.status_code==400,result.text
    assert prefs.read_config()==before and db.settings()['capacity_gb']==before['settings']['capacity_gb']
    assert not (root/'must-not-create').exists()

def test_stale_editor_cannot_overwrite_new_settings(system,client):
    db,prefs,p,root=system
    r=client.get('/configuration').json();prefs.save_settings({'duration':150})
    result=client.put('/configuration/save',json={'revision':r['revision'],'settings':{'capacity_gb':30}})
    assert result.status_code==409
    assert db.settings()['duration']==150 and db.settings()['capacity_gb']==r['config']['settings']['capacity_gb']

def test_queue_conflict_preserves_all_drafts(system,client):
    db,prefs,p,root=system
    from server.queue import enqueue
    enqueue('lofi',150)
    r=client.get('/configuration').json();styles=copy.deepcopy(r['config']['styles']);styles[0]['name']='New name'
    assert client.put('/configuration/save',json={'revision':r['revision'],'styles':styles,'settings':{'capacity_gb':30}}).status_code==409
    assert prefs.read_config()==r['config']
    # Ordinary playback/storage preferences remain editable during generation.
    assert client.put('/configuration/save',json={'revision':r['revision'],'settings':{'capacity_gb':30}}).status_code==200

def test_failed_config_write_rolls_back_sqlite(system,monkeypatch):
    db,prefs,p,root=system
    before=prefs.read_config();revision=prefs.configuration_revision();original=prefs.write_config
    def failing_write(value):
        if value!=before:raise OSError('simulated full disk')
        original(value)
    monkeypatch.setattr(prefs,'write_config',failing_write)
    with pytest.raises(OSError):prefs.commit_configuration({'capacity_gb':30},None,{},revision)
    assert db.settings()['capacity_gb']==before['settings']['capacity_gb'] and prefs.read_config()==before
