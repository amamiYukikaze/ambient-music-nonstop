"""Recovery exercises real JSON, SQLite and API startup in disposable data roots."""
import importlib
import json
import sys

import pytest


def boot(root, monkeypatch):
    monkeypatch.setenv('AMBIENT_DATA_DIR', str(root))
    monkeypatch.setenv('AMBIENT_NO_WORKER', '1')
    for name in list(sys.modules):
        if name == 'server' or name.startswith('server.'):
            del sys.modules[name]
    db = importlib.import_module('server.database')
    db.initialize()
    return db, importlib.import_module('server.preferences')


@pytest.mark.parametrize('damaged',[False,True])
def test_independent_qc_process_loads_model_paths_without_recovering_jobs_or_writing_config(tmp_path,monkeypatch,damaged):
    import subprocess
    from pathlib import Path
    db,prefs=boot(tmp_path,monkeypatch)
    config=prefs.read_config();config['paths']['models']=str(tmp_path/'External Models')
    prefs.write_config(config);prefs.write_config(config)
    with db.connection() as connection:
        connection.execute("INSERT INTO jobs(id,style,status,created,updated,params) VALUES('worker-test','lofi','processing','now','now','{}')")
    if damaged:(tmp_path/'config.json').write_text('{broken')
    before={p.name:p.read_bytes() for p in tmp_path.glob('config*.json')}
    code="from server.preferences import load_worker_config; load_worker_config(); from server.config import model_root; print(model_root('clap'))"
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()==str(tmp_path/'External Models/clap')
    assert db.rows("SELECT status FROM jobs WHERE id='worker-test'")[0]['status']=='processing'
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('config*.json')}


@pytest.mark.parametrize('document', [None, '{broken', 'null', '{}', '{"version":1}',
                                     '{"version":999,"settings":{}}'])
def test_recovery_survives_import_and_api_start(tmp_path, monkeypatch, document):
    config = tmp_path / 'config.json'
    if document is not None:
        config.write_text(document, encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    recovered = prefs.read_config()
    assert recovered['version'] == prefs.CONFIG_VERSION
    assert recovered['settings']['auto_generate'] is False
    assert recovered['setup']['complete'] is False
    assert set(recovered['paths']) >= {'models', 'images', 'ambience'}
    from fastapi.testclient import TestClient
    from server.app import app, TOKEN
    with TestClient(app) as client:
        client.headers['x-ambient-token'] = TOKEN
        health = client.get('/health')
        assert health.status_code == 200
        if document is not None:
            assert health.json()['config_recovery']['status'] == 'recovered'
        assert client.get('/setup').status_code == 200
        assert client.get('/configuration').status_code == 200
    saved = config.read_bytes()
    boot(tmp_path, monkeypatch)
    assert config.read_bytes() == saved, 'Recovery must stabilize after one startup'
    if document is not None:
        originals = list(tmp_path.glob('config.rejected-*.json'))
        assert any(p.read_text(encoding='utf8') == document for p in originals)
        assert recovered['recovery']['status'] == 'recovered'


@pytest.mark.parametrize('version', [1, 2])
def test_supported_and_current_valid_config_preserve_preferences(tmp_path, monkeypatch, version):
    db, prefs = boot(tmp_path, monkeypatch)
    config = prefs.read_config()
    config.update(version=version)
    config['settings'].update(duration=123, auto_generate=True)
    config['setup']['complete'] = True
    (tmp_path / 'config.json').write_text(json.dumps(config), encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert prefs.read_config()['version'] == prefs.CONFIG_VERSION
    assert db.settings()['duration'] == 123
    assert db.settings()['auto_generate'] is True
    assert not list(tmp_path.glob('config.rejected-*.json'))


def test_last_good_and_sqlite_path_survive_corrupt_config(tmp_path, monkeypatch):
    db, prefs = boot(tmp_path, monkeypatch)
    library = tmp_path / 'registered music'
    prefs.save_settings({'library_path': str(library), 'duration': 123})
    prefs.write_config(prefs.read_config())
    (tmp_path / 'config.json').write_text('{broken', encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert db.settings()['library_path'] == str(library)
    assert db.settings()['duration'] == 123
    assert prefs.read_config()['recovery']['source'] == 'last-known-good'
    assert db.settings()['auto_generate'] is False


def test_partial_config_keeps_library_and_asset_paths(tmp_path, monkeypatch):
    library = tmp_path / 'existing music'
    library.mkdir()
    original = library / 'keep.opus'
    original.write_bytes(b'original audio')
    custom = tmp_path / 'custom images'
    (tmp_path / 'config.json').write_text(json.dumps({
        'version': 1, 'settings': {'library_path': str(library), 'duration': 123},
        'paths': {'images': str(custom)},
    }), encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert db.settings()['library_path'] == str(library)
    assert prefs.read_config()['paths']['images'] == str(custom)
    assert original.read_bytes() == b'original audio'
    assert db.settings()['auto_generate'] is False


def test_committed_empty_library_path_overrules_stale_backup(tmp_path, monkeypatch):
    db, prefs = boot(tmp_path, monkeypatch)
    new_library = tmp_path / 'committed destination'
    with db.connection() as con:
        con.execute('UPDATE settings SET value=? WHERE key=?',
                    (json.dumps(str(new_library)), 'library_path'))
    (tmp_path / 'config.json').write_text('null', encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert prefs.read_config()['settings']['library_path'] == str(new_library)
    assert db.settings()['library_path'] == str(new_library)


@pytest.mark.parametrize('field,value', [('styles', [None]), ('settings', None),
                                        ('paths', []), ('setup', {'complete': 'yes'}),
                                        ('images', [None]), ('ambience', {})])
def test_invalid_fields_cannot_kill_startup(tmp_path, monkeypatch, field, value):
    db, prefs = boot(tmp_path, monkeypatch)
    config = prefs.read_config()
    config[field] = value
    (tmp_path / 'config.json').write_text(json.dumps(config), encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert prefs.read_config()['recovery']['status'] == 'recovered'
    assert isinstance(prefs.read_config()['settings'], dict)


def test_live_file_damage_cannot_kill_running_service(tmp_path, monkeypatch):
    db, prefs = boot(tmp_path, monkeypatch)
    saved = prefs.read_config()
    (tmp_path / 'config.json').write_text('null', encoding='utf8')
    assert prefs.read_config() == saved
    # A later save must preserve the damaged on-disk original for diagnosis too.
    prefs.save_settings({'duration': 122})
    assert any(p.read_text(encoding='utf8') == 'null' for p in tmp_path.glob('config.rejected-*.json'))


def test_custom_style_survives_restart(tmp_path, monkeypatch):
    db, prefs = boot(tmp_path, monkeypatch)
    styles = prefs.read_config()['styles']
    custom = dict(styles[0], id='custom_style', name='Custom')
    prefs.replace_styles([*styles, custom])
    prefs.save_settings({'enabled_styles': ['custom_style']})
    db, prefs = boot(tmp_path, monkeypatch)
    assert 'custom_style' in importlib.import_module('server.config').STYLE_MAP
    assert db.settings()['enabled_styles'] == ['custom_style']


def test_failed_atomic_replace_retains_last_good_and_database(tmp_path, monkeypatch):
    from pathlib import Path
    db, prefs = boot(tmp_path, monkeypatch)
    before = prefs.read_config()
    original = Path.replace
    def fail_config_replace(path, target):
        if target == tmp_path / 'config.json':
            raise OSError('injected disk write failure')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', fail_config_replace)
    with pytest.raises(OSError, match='injected'):
        prefs.save_settings({'duration': 120})
    assert prefs.read_config() == before
    assert json.loads((tmp_path / 'config.json').read_text(encoding='utf8')) == before
    assert json.loads((tmp_path / 'config.last-good.json').read_text(encoding='utf8')) == before
    assert db.settings()['duration'] == before['settings']['duration']


def test_future_config_is_preserved_with_registered_library(tmp_path, monkeypatch):
    library = tmp_path / 'future music'
    original = json.dumps({'version': 999, 'settings': {'library_path': str(library)}, 'future': [1, 2]})
    (tmp_path / 'config.json').write_text(original, encoding='utf8')
    db, prefs = boot(tmp_path, monkeypatch)
    assert db.settings()['library_path'] == str(library)
    assert str(library) in prefs.read_config()['recovery']['library_paths']
    assert any(p.read_text(encoding='utf8') == original for p in tmp_path.glob('config.rejected-*.json'))
