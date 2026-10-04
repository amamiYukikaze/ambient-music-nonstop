import hashlib
import json
import numpy as np
import pytest
from test_settings_v11 import system


def prepare(system,monkeypatch):
    db,prefs,p,root=system
    config=prefs.read_config()
    config['setup'].update(models_verified=True,models=['acestep-v15-turbo'],
                           hardware={'ace':True,'sa3':False,'gpus':[{'vram_gb':4}]})
    prefs.write_config(config)
    monkeypatch.setattr(p,'model_status',lambda:[{'id':'acestep-v15-turbo','installed':True,'eligible':True}])
    monkeypatch.setattr(p.shutil,'disk_usage',lambda _:type('Disk',(),{'free':100_000_000_000})())
    from server.config import STYLE_MAP
    return {s:100 if s=='lofi' else 0 for s in STYLE_MAP}


def publish(system,job_id):
    db,prefs,p,root=system
    from server.queue import Producer
    job=db.rows('SELECT * FROM jobs WHERE id=?',(job_id,))[0]
    work=root/'staging'/job_id;work.mkdir(exist_ok=True)
    source=work/'normalized.opus';source.write_bytes(b'accepted fixture '+job_id.encode())
    np.ones(4,dtype='<f4').tofile(work/'embedding.bin')
    np.zeros((12,64),dtype='<f4').tofile(work/'fingerprint.bin')
    qc={'qc':{'final':{'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'duration':180,'lufs':-18}},'analysis':{}}
    Producer().promote(job,json.loads(job['params']),{'model':'fixture'},qc,work)


def test_failed_first_publication_retries_same_owned_directory_and_refills(system,monkeypatch):
    db,prefs,p,root=system;weights=prepare(system,monkeypatch)
    library=root/'music'
    first=p.begin_first(str(library),weights,['lofi'])['first_job']['id']
    monkeypatch.setattr(p.shutil,'disk_usage',lambda _:type('Disk',(),{'free':1})())
    publish(system,first)
    assert db.rows('SELECT status FROM jobs WHERE id=?',(first,))[0]['status']=='failed'
    assert (library/'lofi').is_dir() and not list((library/'lofi').iterdir())
    monkeypatch.setattr(p.shutil,'disk_usage',lambda _:type('Disk',(),{'free':100_000_000_000})())
    second=p.begin_first(str(library),weights,['lofi'])['first_job']['id']
    publish(system,second)
    assert p.setup_status()['setup']['complete']
    assert db.settings()['auto_generate'] is True
    from server.queue import Producer
    Producer().refill()
    assert db.rows("SELECT id FROM jobs WHERE status='queued'")
    prefs.save_settings({'auto_generate':False})
    p.setup_status()
    assert db.settings()['auto_generate'] is False, 'Later status polling must respect an intentional pause'


@pytest.mark.parametrize('foreign',['notes.txt','lofi/keep.opus','unrelated'])
def test_retry_cannot_adopt_foreign_files_or_directories(system,monkeypatch,foreign):
    db,prefs,p,root=system;weights=prepare(system,monkeypatch)
    library=root/'music'
    first=p.begin_first(str(library),weights,['lofi'])['first_job']['id']
    with db.connection() as con:con.execute("UPDATE jobs SET status='failed' WHERE id=?",(first,))
    extra=library/foreign;extra.parent.mkdir(parents=True,exist_ok=True)
    if foreign=='unrelated':extra.mkdir()
    else:extra.write_bytes(b'user content')
    with pytest.raises(ValueError,match='空目录|已有文件|残留'):
        p.begin_first(str(library),weights,['lofi'])
    assert extra.exists()


def test_first_job_done_without_ready_qc_track_cannot_complete_setup(system,monkeypatch):
    db,prefs,p,root=system;weights=prepare(system,monkeypatch)
    first=p.begin_first(str(root/'music'),weights,['lofi'])['first_job']['id']
    with db.connection() as con:con.execute("UPDATE jobs SET status='done' WHERE id=?",(first,))
    assert not p.setup_status()['setup']['complete']
    assert db.settings()['auto_generate'] is False
