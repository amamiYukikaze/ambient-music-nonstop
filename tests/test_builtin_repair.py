import hashlib
import json
from pathlib import Path
import pytest
from test_settings_v11 import system


def test_restart_repairs_missing_and_corrupt_builtins_but_preserves_other_files(system):
    db,_,_,data=system
    directory=data/'Ambience';manifest=json.loads((directory/'manifest.json').read_text())
    missing=directory/manifest[0]['file'];missing.unlink()
    corrupt=directory/manifest[1]['file'];corrupt.write_bytes(b'old user modified bytes')
    extra=directory/'personal.wav';extra.write_bytes(b'keep original')
    (directory/'manifest.json').write_text('{incomplete')
    db.initialize()
    assert hashlib.sha256(missing.read_bytes()).hexdigest()==manifest[0]['sha256']
    assert hashlib.sha256(corrupt.read_bytes()).hexdigest()==manifest[1]['sha256']
    assert extra.read_bytes()==b'keep original'
    assert any(p.read_bytes()==b'old user modified bytes' for p in (directory/'.recovery').iterdir())
    assert json.loads((directory/'manifest.json').read_text())==manifest
    before={p.name:p.read_bytes() for p in (directory/'.recovery').iterdir()}
    db.initialize()
    assert before=={p.name:p.read_bytes() for p in (directory/'.recovery').iterdir()}


def test_untrusted_package_and_failed_copy_never_commit_manifest(tmp_path,monkeypatch):
    from server.builtin_assets import repair_builtins
    source=tmp_path/'packaged';source.mkdir();target=tmp_path/'installed';target.mkdir()
    file=source/'rain.opus';file.write_bytes(b'good source')
    manifest=[{'id':'rain','file':'rain.opus','sha256':hashlib.sha256(file.read_bytes()).hexdigest()}]
    (source/'manifest.json').write_text(json.dumps(manifest));(target/'manifest.json').write_bytes(b'old manifest')
    file.write_bytes(b'corrupted source')
    with pytest.raises(ValueError,match='checksum'):repair_builtins(source,target)
    assert (target/'manifest.json').read_bytes()==b'old manifest'
    file.write_bytes(b'good source')
    original=Path.open
    def fail(path,*args,**kwargs):
        if '.part-' in path.name and 'w' in args[0]:raise OSError('injected disk failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',fail)
    with pytest.raises(OSError,match='disk failure'):repair_builtins(source,target)
    assert (target/'manifest.json').read_bytes()==b'old manifest'
    assert not list(target.glob('*.part-*'))
