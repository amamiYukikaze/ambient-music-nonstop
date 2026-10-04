import importlib.util
import json
import sys
from pathlib import Path


def cache_module():
    path = Path(__file__).resolve().parents[1] / 'scripts/runtime_cache.py'
    spec = importlib.util.spec_from_file_location('runtime_cache_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path, monkeypatch):
    cache = cache_module()
    for folder in ('vendor', '.venv-sa3-py311', 'tools'):
        (tmp_path / folder).mkdir()
    dependency = tmp_path / 'vendor/dependency.py'
    dependency.write_text('working', encoding='utf8')
    monkeypatch.setattr(cache, 'identity', lambda *_: {'receipt': 'verified', 'verifier': 1})
    monkeypatch.setattr(cache, 'driver_identity', lambda: 'GPU-1,driver-1')
    spec = tmp_path / 'spec.json'
    calls = []
    def full():
        calls.append(True)
        return {'ok': dependency.exists() and dependency.read_text() == 'working', 'errors': []}
    return cache, dependency, spec, calls, full


def test_validated_restart_skips_all_import_probes(tmp_path, monkeypatch):
    cache, _, spec, calls, full = fixture(tmp_path, monkeypatch)
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'full'
    result = cache.startup_check(tmp_path, spec, full)
    assert result['mode'] == 'cached' and result['files'] == 1
    assert len(calls) == 1


def test_modified_or_deleted_dependency_never_uses_cache(tmp_path, monkeypatch):
    cache, dependency, spec, calls, full = fixture(tmp_path, monkeypatch)
    cache.startup_check(tmp_path, spec, full)
    dependency.write_text('damaged')
    assert not cache.startup_check(tmp_path, spec, full)['ok']
    dependency.unlink()
    assert not cache.startup_check(tmp_path, spec, full)['ok']
    assert len(calls) == 3


def test_new_dependency_driver_or_verifier_invalidates_cache(tmp_path, monkeypatch):
    cache, _, spec, calls, full = fixture(tmp_path, monkeypatch)
    cache.startup_check(tmp_path, spec, full)
    (tmp_path / 'tools/new.dll').write_bytes(b'new')
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'full'
    monkeypatch.setattr(cache, 'driver_identity', lambda: 'GPU-1,driver-2')
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'full'
    monkeypatch.setattr(cache, 'identity', lambda *_: {'receipt': 'verified', 'verifier': 2})
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'full'
    assert len(calls) == 4


def test_interrupted_install_or_malformed_cache_cannot_pass(tmp_path, monkeypatch):
    cache, _, spec, calls, full = fixture(tmp_path, monkeypatch)
    cache.startup_check(tmp_path, spec, full)
    (tmp_path / cache.CACHE_NAME).write_text('{broken')
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'full'
    (tmp_path / '.runtime-installing').touch()
    assert not cache.startup_check(tmp_path, spec, full)['ok']
    assert len(calls) == 2


def test_bytecode_is_not_a_dependency_change_but_racing_installer_is(tmp_path, monkeypatch):
    cache, dependency, spec, calls, full = fixture(tmp_path, monkeypatch)
    cache.startup_check(tmp_path, spec, full)
    pycache = tmp_path / 'vendor/__pycache__'; pycache.mkdir()
    (pycache / 'dependency.pyc').write_bytes(b'compiled')
    assert cache.startup_check(tmp_path, spec, full)['mode'] == 'cached'
    (tmp_path / cache.CACHE_NAME).unlink()
    def racing_full():
        dependency.write_text('concurrently changed')
        return {'ok': True, 'errors': []}
    assert not cache.startup_check(tmp_path, spec, racing_full)['ok']
    assert not (tmp_path / cache.CACHE_NAME).exists()


def test_identity_requires_current_install_receipt_and_hashes_controls(tmp_path):
    cache = cache_module()
    spec = tmp_path / 'runtime-spec.json'
    spec.write_text(json.dumps({'runtime_version': 1, 'lock_sha256': {'lock.txt': 'unused'}}))
    (tmp_path / 'scripts').mkdir();lock = tmp_path / 'scripts/lock.txt';lock.write_text('version-1')
    receipt = tmp_path / 'runtime.json'
    receipt.write_text(json.dumps({'schema_version': 1, 'runtime_version': 1, 'spec_sha256': cache.file_hash(spec)}))
    original = cache.identity(tmp_path, spec)
    lock.write_text('version-2')
    assert cache.identity(tmp_path, spec) != original
    receipt.write_text('{}')
    import pytest
    with pytest.raises(ValueError, match='outdated'):
        cache.identity(tmp_path, spec)


def test_install_completion_seeds_cache_but_marker_still_blocks_startup(tmp_path, monkeypatch):
    cache = cache_module()
    monkeypatch.setitem(sys.modules, 'runtime_cache', cache)
    monkeypatch.setattr(cache, 'driver_identity', lambda: 'GPU-1,driver-1')
    module_spec = importlib.util.spec_from_file_location('health_install_test',
        Path(__file__).resolve().parents[1] / 'scripts/runtime_health.py')
    health = importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(health)
    monkeypatch.setattr(health.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(health.platform, 'machine', lambda: 'AMD64')
    for name in ('vendor', '.venv-sa3-py311', 'tools/ffmpeg/bin', 'tools/uv'):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name in ('ffmpeg', 'ffprobe'):
        file = tmp_path / f'tools/ffmpeg/bin/{name}.exe';file.write_bytes(name.encode())
        checksums[name] = cache.file_hash(file)
    uv = tmp_path / 'tools/uv/uv.exe';uv.write_bytes(b'uv')
    spec_path = tmp_path / 'spec.json'
    spec_path.write_text(json.dumps({'schema_version': 1, 'runtime_version': 1,
        'sources': {}, 'environments': {}, 'lock_sha256': {},
        'ffmpeg': {'version': '1.0', 'executables': checksums},
        'uv': {'version': '1.0', 'executable_sha256': cache.file_hash(uv)}}))
    monkeypatch.setattr(health, 'command', lambda args, *_: Path(args[0]).stem + (' 1.0 build' if Path(args[0]).stem == 'uv' else ' version 1.0'))
    marker = tmp_path / '.runtime-installing';marker.touch()
    assert health.check_runtime(tmp_path, spec_path, complete_install=True)['ok']
    assert (tmp_path / cache.CACHE_NAME).exists()
    def unexpected_check():
        raise AssertionError('installation was already fully checked')
    assert not cache.startup_check(tmp_path, spec_path, unexpected_check)['ok']
    marker.unlink()
    assert cache.startup_check(tmp_path, spec_path, unexpected_check)['mode'] == 'cached'
