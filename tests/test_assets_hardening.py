import concurrent.futures
import threading
import wave
from pathlib import Path
import pytest
from test_settings_v11 import system


def wav(path,seconds):
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000)
        output.writeframes(b'\0'*(8000*2*seconds))


def test_concurrent_imports_keep_both_real_conversions(system,monkeypatch):
    from PIL import Image
    from server.assets import import_asset
    root=system[3];source=root/'source.png';Image.new('RGB',(16,16),'blue').save(source)
    barrier=threading.Barrier(2);save=Image.Image.save
    def synchronized(image,*args,**kwargs):
        result=save(image,*args,**kwargs);barrier.wait(timeout=10);return result
    monkeypatch.setattr(Image.Image,'save',synchronized)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        rows=list(executor.map(lambda i:import_asset('images',str(source),f'image {i}'),range(2)))
    registered=system[1].read_config()['images']
    assert {r['id'] for r in registered}=={r['id'] for r in rows}
    assert all(Path(r['path']).is_file() for r in registered)


def test_failed_index_commit_removes_only_new_conversion(system,monkeypatch):
    from PIL import Image
    from server import assets,preferences
    root=system[3];source=root/'original.png';Image.new('RGB',(16,16),'blue').save(source)
    original=source.read_bytes()
    def fail(*args,**kwargs):raise OSError('injected config write failure')
    monkeypatch.setattr(preferences,'write_config',fail)
    with pytest.raises(OSError):assets.import_asset('images',str(source),'test')
    assert source.read_bytes()==original
    assert not list((root/'Images').glob('*.webp'))
    assert preferences.read_config()['images']==[]


def test_overlong_import_and_preexisting_long_media_are_rejected_before_transfer(system):
    from server import assets
    db,prefs,p,root=system
    source=root/'long.wav';wav(source,181)
    with pytest.raises(ValueError,match='3 分钟'):
        assets.import_asset('ambience',str(source),'too long')
    config=prefs.read_config();config['ambience']=[{'id':'custom_'+'a'*32,'path':str(source),'name':'old long audio'}];prefs.write_config(config)
    from fastapi.testclient import TestClient
    from server.app import app,TOKEN
    with TestClient(app,headers={'x-ambient-token':TOKEN}) as client:
        for url in ['/ambience/custom_'+'a'*32,'/ambience/custom_'+'a'*32+'/info']:
            response=client.get(url);assert response.status_code==413,response.text
    assert source.is_file()


def test_imported_recording_is_bounded_and_original_is_unchanged(system):
    from server import assets
    from server.qc import probe
    root=system[3];source=root/'short.wav';wav(source,3);before=source.read_bytes()
    row=assets.import_asset('ambience',str(source),'short')
    info=probe(Path(row['path']))
    # Opus records 48 kHz in its container; renderer decodes at the declared budget rate.
    assert info['channels']<=2 and info['duration']<3.25
    assert source.read_bytes()==before
    details=assets.ambience_info(row['id'])
    assert details['decode_sample_rate']==24000
    assert details['decoded_bytes']<1024*1024
