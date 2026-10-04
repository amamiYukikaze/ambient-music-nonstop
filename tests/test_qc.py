"""Real FFmpeg tests on synthetic fixtures, kept separate from AI acceptance evidence."""
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from server.qc import inspect,normalize,Rejection,loudness
from server.qc import edge_trim


def test_silent_clipped_truncated_and_valid_signal(tmp_path):
    sr=48000;t=np.arange(sr*24)/sr
    p=tmp_path/'test.wav'
    sf.write(p,np.zeros(len(t)),sr)
    with pytest.raises(Rejection,match='silent'):inspect(p,24)
    sf.write(p,np.sign(np.sin(2*np.pi*220*t)),sr)
    with pytest.raises(Rejection,match='clipping'):inspect(p,24)
    sf.write(p,.08*np.sin(2*np.pi*220*t),sr)
    with pytest.raises(Rejection,match='duration'):inspect(p,60)
    metrics=normalize(p,tmp_path/'test.opus',24)
    assert abs(metrics['final']['lufs']+18)<.7
    assert metrics['final']['true_peak_db']<=-.7
    assert metrics['final']['channels']==2


def test_corrupted_file_is_processing_failure(tmp_path):
    p=tmp_path/'broken.wav';p.write_bytes(b'not an audio file')
    with pytest.raises(RuntimeError):inspect(p)


def test_edge_trim_silence_fade_and_active_stereo(tmp_path):
    sr=24000;t=np.arange(sr*30)/sr
    active=.1*np.sin(2*np.pi*220*t)
    stereo=np.column_stack([active,-active])
    assert edge_trim(stereo,sr)==(0.,0.), 'opposite phase must not cancel to silence'
    stereo[:sr*2]=0;stereo[-sr*3:]=0
    head,tail=edge_trim(stereo,sr)
    assert 1.9<head<2.0 and 2.9<tail<=3.0
    source=tmp_path/'edge.wav';sf.write(source,stereo,sr)
    result=normalize(source,tmp_path/'edge.opus',30)
    assert 24.9<result['final']['duration']<25.3
    assert result['edge_edit']['head_seconds']==head
    assert abs(result['final']['lufs']+18)<.7
    fade=np.minimum(t/5,1)*np.minimum((30-t)/5,1)
    a,b=edge_trim(np.column_stack([active*fade,active*fade]),sr)
    assert .8<a<2 and .8<b<2


def test_edge_trim_never_removes_more_than_three_seconds():
    sr=1000;y=np.ones((30000,2))*.1;y[:5000]=0;y[-5000:]=0
    assert edge_trim(y,sr)==(3.,3.)


def test_flac_is_real_24_bit_and_normalized(tmp_path):
    sr=48000;t=np.arange(sr*24)/sr;p=tmp_path/'source.wav';dest=tmp_path/'music.flac'
    sf.write(p,.07*np.sin(2*np.pi*220*t)+.02*np.sin(2*np.pi*880*t),sr)
    result=normalize(p,dest,24,{'codec':'flac','bits':24})
    assert sf.info(dest).subtype=='PCM_24'
    assert sf.info(dest).samplerate==48000
    assert abs(result['final']['lufs']+18)<.7


def test_style_screen_rejects_lofi_and_accepts_reference_direction():
    from server.style_qc import inspect_style,require_style
    from server.qc import Rejection as StyleRejection
    bank=np.load(Path(__file__).resolve().parents[1]/'server/style_reference_v5.npz')
    lofi=bank['text_vectors'][list(bank['text_labels']).index('lofi')]
    for style in ['guitar','artcore','daily_piano','anime_daily']:
        with pytest.raises(StyleRejection,match='style_mismatch'):require_style(inspect_style(lofi,style))
        # Public source has text vectors only; private audio prototypes are
        # optional diagnostics and are never needed by this gate regression.
        target=bank['text_vectors'][list(bank['text_labels']).index(style)]
        require_style(inspect_style(target,style))


def test_lossless_static_gain_preserves_large_dynamic_contrast(tmp_path):
    sr=24000;t=np.arange(sr*30)/sr
    envelope=np.where(t<15,.012,.18)
    signal=envelope*(np.sin(2*np.pi*220*t)+.2*np.sin(2*np.pi*440*t))
    source=tmp_path/'dynamic.wav';dest=tmp_path/'dynamic.flac';sf.write(source,signal,sr,subtype='FLOAT')
    result=normalize(source,dest,30,{'codec':'flac','bits':24,'preserve_dynamics':True})
    decoded,sr=sf.read(dest)
    # Compare two interior sections, away from trimmed edges and microfades.
    ratio=np.sqrt(np.mean(decoded[18*sr:23*sr]**2))/np.sqrt(np.mean(decoded[4*sr:9*sr]**2))
    assert abs(ratio-15)<.01
    assert result['final']['true_peak_db']<=-.7
    assert abs(result['final']['lufs']-result['loudness_target'])<.7
    assert sf.info(dest).subtype=='PCM_24'


def test_dynamic_archive_accepts_quieter_peak_limited_target(tmp_path):
    sr=24000;t=np.arange(sr*24)/sr
    signal=.009*np.sin(2*np.pi*220*t)
    # A brief natural-looking transient makes -18 LUFS impossible without limiting.
    at=sr*12;signal[at:at+240]+=.75*np.hanning(240)*np.sin(2*np.pi*900*t[:240])
    source=tmp_path/'transient.wav';dest=tmp_path/'transient.flac';sf.write(source,signal,sr,subtype='FLOAT')
    result=normalize(source,dest,24,{'codec':'flac','bits':24,'preserve_dynamics':True})
    assert result['peak_limited'] and result['loudness_target'] < -18
    assert abs(result['final']['lufs']-result['loudness_target'])<.7
    assert result['final']['true_peak_db']<=-.7


def test_sa3_preserves_musical_edges_and_lossless_format(tmp_path):
    sr=24000;t=np.arange(sr*24)/sr
    y=.08*np.sin(2*np.pi*220*t);y[:sr]=0;y[-sr*2:]=0
    source=tmp_path/'sa3.wav';dest=tmp_path/'sa3.flac';sf.write(source,y,sr)
    result=normalize(source,dest,24,{'codec':'flac','preserve_dynamics':True,'preserve_edges':True})
    assert result['final']['duration']==24
    assert result['edge_edit']['head_seconds']==result['edge_edit']['tail_seconds']==0
    assert sf.info(dest).subtype=='PCM_24'
