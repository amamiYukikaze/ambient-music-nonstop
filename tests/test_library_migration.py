"""Real filesystem transfers on disposable libraries; production is never moved."""
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from test_lifecycle import system,add_track


def test_windows_junction_destination_and_source_are_rejected(system,tmp_path):
    import os,subprocess
    if os.name!='nt':pytest.skip('Windows junction regression')
    _,_,_,cfg=system;add_track(system)
    from server.migration import manager
    outside=tmp_path/'outside';outside.mkdir();sentinel=outside/'mine.txt';sentinel.write_bytes(b'keep')
    junction=tmp_path/'junction'
    script=tmp_path/'make-junction.ps1'
    script.write_text('param($Link,$Target)\n$ErrorActionPreference="Stop"\nNew-Item -ItemType Junction -Path $Link -Target $Target | Out-Null')
    def make(link):
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                        '-File',str(script),str(link),str(outside)],check=True,capture_output=True)
    make(junction)
    try:
        with pytest.raises(ValueError,match='链接|联接'):manager.validate(str(junction/'child'))
        # The scan must refuse reparse directories even when they point to an empty folder.
        child=cfg.library_root()/'linked'
        make(child)
        try:
            with pytest.raises(ValueError,match='链接|联接'):manager.scan(cfg.library_root(),tmp_path/'target')
        finally:os.rmdir(child)
    finally:os.rmdir(junction)
    assert sentinel.read_bytes()==b'keep'


@pytest.mark.parametrize('content',['{broken','null','{}','{"phase":"done","total_bytes":"bad"}',
                                    '{"phase":"failed","recovery_error":true,"work_bytes":null}'])
def test_damaged_migration_journal_is_preserved_without_breaking_startup(system,content):
    _,_,_,cfg=system;original=add_track(system)
    from server.migration import LibraryMigration
    journal=cfg.DATA/'library-migration.json';journal.write_text(content)
    manager=LibraryMigration();manager.restore()
    assert not manager.active and manager.snapshot()['phase']=='failed'
    assert original.read_bytes()==b'fixture'
    assert any(p.read_text()==content for p in cfg.DATA.glob('library-migration.rejected-*.json'))


def finish(manager):
    manager.thread.join(10)
    assert not manager.thread.is_alive(), 'Migration deadlocked'
    return manager.snapshot()


def test_move_preserves_media_review_sidecars_and_restart(system,tmp_path):
    db,lib,q,cfg=system
    from server.migration import manager,digest
    old=add_track(system);review=add_track(system,'b'*32,'guzheng')
    with db.connection() as c:c.execute("UPDATE tracks SET status='review' WHERE id=?",('b'*32,))
    source=cfg.library_root();expected={p.relative_to(source):digest(p) for p in source.rglob('*') if p.is_file()}
    model=cfg.DATA/'models/keep.bin';model.write_bytes(b'untouched')
    destination=tmp_path/'new music';manager.start(str(destination));result=finish(manager)
    assert result['phase']=='done',result
    assert result['progress']==100 and not source.exists()
    assert expected=={p.relative_to(destination):digest(p) for p in destination.rglob('*') if p.is_file()}
    assert cfg.library_root()==destination and model.read_bytes()==b'untouched'
    assert all(Path(r['path']).is_relative_to(destination) for r in db.rows('SELECT path FROM tracks'))
    db.initialize();assert not source.exists()
    lib.start_play('a'*32);lib.write_sidecar('a'*32)
    from server.app import audio
    assert Path(audio('a'*32).path).is_file()
    assert lib.retire('a'*32) and not (destination/old.relative_to(source)).exists()
    assert (destination/review.relative_to(source)).exists()


def test_copy_failure_preserves_source_and_retry(system,tmp_path):
    _,_,_,cfg=system;old=add_track(system)
    from server.migration import manager
    target=tmp_path/'copy-target';original=Path.open
    def fail(self,*a,**kw):
        if self.name.endswith('.part') and a and a[0]=='wb':raise OSError('injected destination failure')
        return original(self,*a,**kw)
    with patch.object(Path,'open',fail):
        manager.start(str(target));result=finish(manager)
    assert result['phase']=='failed' and old.exists() and cfg.library_root()!=target
    manager.start(str(target));assert finish(manager)['phase']=='done'
    assert not old.exists()


def test_corrupt_copy_never_switches_or_deletes(system,tmp_path):
    _,_,_,cfg=system;old=add_track(system)
    from server.migration import manager
    target=tmp_path/'corrupt-target';persist=manager.persist
    def corrupt(force=False,**values):
        if values.get('phase')=='verifying':(target/'lofi'/old.name).write_bytes(b'corrupted')
        return persist(force,**values)
    with patch.object(manager,'persist',corrupt):
        manager.start(str(target));result=finish(manager)
    assert result['phase']=='failed' and '校验失败' in result['error']
    assert old.read_bytes()==b'fixture' and cfg.library_root()!=target
    manager.start(str(target));assert finish(manager)['phase']=='done'


def test_committed_cleanup_failure_resumes_after_restart(system,tmp_path):
    _,_,_,cfg=system;old=add_track(system)
    from server.migration import manager,LibraryMigration
    target=tmp_path/'cleanup-target';unlink=Path.unlink
    def locked(self,*a,**kw):
        if self==old:raise PermissionError('injected old media lock')
        return unlink(self,*a,**kw)
    with patch.object(Path,'unlink',locked):
        manager.start(str(target));assert finish(manager)['phase']=='failed'
    assert cfg.library_root()==target and old.exists()
    restored=LibraryMigration();restored.restore();assert finish(restored)['phase']=='done'
    assert not old.exists()


def test_unsafe_destinations_and_foreign_content_are_rejected(system,tmp_path):
    _,_,_,cfg=system;add_track(system)
    from server.migration import manager
    occupied=tmp_path/'occupied';occupied.mkdir();(occupied/'mine.txt').write_text('mine')
    for target in [cfg.library_root(),cfg.library_root()/'child',tmp_path,cfg.DATA/'models/new',occupied,Path('relative')]:
        with pytest.raises(ValueError):manager.start(str(target))
    assert (occupied/'mine.txt').read_text()=='mine'


def test_waiting_for_inference_blocks_api_but_not_publication_gate(system,tmp_path):
    db,_,_,cfg=system;add_track(system)
    from server.migration import manager
    from server.locks import InferenceLease
    from server.operation_lock import gate
    from server.app import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        client.headers['x-ambient-token']='test-token-not-a-secret'
        with InferenceLease():
            assert client.post('/library-move',json={'destination':str(tmp_path/'waiting')}).status_code==200
            time.sleep(.1)
            assert manager.active and manager.state['phase']=='waiting'
            # An existing job can still acquire the publication gate and finish.
            assert gate.acquire(timeout=.5);gate.release()
            for method,route,body in [('GET','/state',None),('GET','/audio/'+'a'*32,None),('POST','/jobs',{}),('PATCH','/settings',{'auto_generate':True})]:
                assert client.request(method,route,json=body).status_code==423
            assert client.get('/library-move').status_code==200
            health=client.get('/health')
            assert health.status_code==200 and health.json()['library_migration']['active']
            assert client.get('/setup').status_code==200
            assert client.post('/setup/device',json={'consent':True}).status_code==423
        assert finish(manager)['phase']=='done'


def test_custom_weights_persist_and_zero_weight_excludes_refill(system):
    db,_,queue,cfg=system
    from server.app import app
    from fastapi.testclient import TestClient
    weights={s:0 for s in cfg.STYLE_MAP};weights['guzheng']=70;weights['guitar']=30
    with TestClient(app) as client:
        client.headers['x-ambient-token']='test-token-not-a-secret'
        assert client.patch('/settings',json={'style_weights':weights}).status_code==200
        assert client.patch('/settings',json={'style_weights':{'lofi':100}}).status_code==400
        assert client.patch('/settings',json={'style_weights':{s:0 for s in weights}}).status_code==400
    db.initialize();assert db.settings()['style_weights']==weights
    counts={s:100 for s in weights};counts['lofi']=0;counts['guzheng']=4;counts['guitar']=5
    assert queue.refill_style(counts,list(weights),weights)=='guzheng'
    assert {r['style'] for r in queue.refill_plan()['priority']}=={'guzheng','guitar'}
