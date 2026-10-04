"""Whole-file signal QC, two-pass loudnorm, final-codec loudness verification."""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np


class Rejection(Exception):
    pass


def run(args, binary=False):
    p = subprocess.run(args,capture_output=True,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf8',errors='replace')[-3000:])
    return p.stdout if binary else p.stderr.decode('utf8',errors='replace')


def probe(path):
    raw = run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],True)
    data = json.loads(raw)
    audio = next(s for s in data['streams'] if s['codec_type']=='audio')
    return dict(duration=float(data['format']['duration']),sample_rate=int(audio['sample_rate']),channels=audio['channels'],codec=audio['codec_name'])


def decode(path, sr=24000, start=None, duration=None, channels=2):
    args = ['ffmpeg','-v','error']
    if start is not None:
        args += ['-ss',str(start)]
    args += ['-i',str(path)]
    if duration is not None:
        args += ['-t',str(duration)]
    # Preserve both channels for clipping detection; mono cancellation can hide defects.
    return np.frombuffer(run(args+['-vn','-ac',str(channels),'-ar',str(sr),'-f','f32le','-'],True),'<f4').reshape(-1,channels)


def inspect(path, expected=None):
    info = probe(path)
    if expected and abs(info['duration']-expected)>max(2,expected*.05):
        raise Rejection(f'duration_mismatch: {info["duration"]:.2f}s expected {expected}s')
    if info['duration']<20 or info['duration']>600:
        raise Rejection('duration_out_of_range')
    if info['channels'] not in (1,2):raise Rejection('unsupported_channel_layout')
    y = decode(path,48000,channels=info['channels'])
    if not len(y) or not np.isfinite(y).all():
        raise Rejection('empty_or_nonfinite_audio')
    peak = float(np.abs(y).max())
    rms = float(np.sqrt(np.mean(y*y)))
    clipped = float(np.mean(np.abs(y)>=.999))
    windows = len(y)//24000
    levels = np.sqrt(np.mean(y[:windows*24000].reshape(windows,-1)**2,axis=1))
    silent = levels < .0001
    longest = current = 0
    for v in silent:
        current = current+1 if v else 0
        longest = max(longest,current)
    if peak<.001 or rms<.0001 or silent.mean()>.45:
        raise Rejection('silent_or_mostly_silent')
    if longest*.5>12:
        raise Rejection('long_silent_gap')
    if clipped>.005 or peak>1.5:
        raise Rejection(f'excessive_clipping: fraction={clipped:.6f}, peak={peak:.4f}')
    info.update(peak=peak,rms_db=20*math.log10(rms),clipping_fraction=clipped,silence_fraction=float(silent.mean()),longest_silence=longest*.5)
    return info


def loudness(path):
    stderr = run(['ffmpeg','-hide_banner','-nostats','-i',str(path),'-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'])
    data = json.loads(re.findall(r'\{[^{}]+\}',stderr)[-1])
    if not all(math.isfinite(float(data[k])) for k in ['input_i','input_tp','input_lra','input_thresh']):
        raise Rejection('nonfinite_loudness')
    return data


def edge_trim(y, sr):
    """Remove only quiet/fading edge runs, capped at 3 s per side.

    Compare stereo energy with the middle of the piece. Never use mono sums:
    opposite-phase stereo must not be mistaken for silence. Keep 60 ms of
    margin, and require 120 ms of sound before deciding an intro has started.
    """
    hop = max(1, round(sr * .01))
    blocks = len(y) // hop
    if blocks < 1000:return (0.0, 0.0)
    rms = np.sqrt(np.mean(y[:blocks*hop].reshape(blocks, -1)**2, axis=1))
    middle = rms[blocks//5:blocks*4//5]
    threshold = max(10**(-50/20), float(np.median(middle)) * .28)
    def scan(values):
        run = 0
        for i, level in enumerate(values[:312]):
            run = run + 1 if level >= threshold else 0
            if run >= 12:return round(max(0, min(3., (i-11)*.01-.06)), 3)
        return 3.0
    return scan(rms), scan(rms[::-1])


def normalize(source, destination, expected, encoding=None):
    encoding=encoding or {'codec':'opus','bitrate_kbps':128}
    raw = inspect(source,expected)
    preserve_edges=bool(encoding.get('preserve_edges'))
    head, tail = (0.,0.) if preserve_edges else edge_trim(decode(source, 24000), 24000)
    length = raw['duration'] - head - tail
    edited = Path(destination).with_name('edge-edited.wav')
    # Edit before normalization and embedding; metadata describes the audible archive.
    run(['ffmpeg','-y','-v','error','-i',str(source),'-af',
         f'atrim=start={head}:end={raw["duration"]-tail},asetpts=PTS-STARTPTS,afade=t=in:d=0.025,afade=t=out:st={length-.025}:d=0.025',
         '-c:a','pcm_f32le',str(edited)])
    source = edited
    m = loudness(source)
    preserve=bool(encoding.get('preserve_dynamics'))
    target_lra=max(11,min(50,float(m['input_lra'])+1)) if preserve else 11
    filt = (f'loudnorm=I=-18:TP=-1.5:LRA={target_lra}:measured_I={m["input_i"]}:'
            f'measured_TP={m["input_tp"]}:measured_LRA={m["input_lra"]}:'
            f'measured_thresh={m["input_thresh"]}:offset={m["target_offset"]}:linear=true')
    # A static gain preserves the pluck/decay envelope. When peak headroom limits
    # it, accept a quieter archive and record that explicitly, never compress it.
    gain=min(-18-float(m['input_i']),-1.5-float(m['input_tp'])) if preserve else None
    target_i=float(m['input_i'])+gain if preserve else -18
    if preserve:filt=f'volume={gain}dB'
    if encoding.get('codec')=='flac':codec=['-c:a','flac','-sample_fmt','s32','-bits_per_raw_sample','24','-compression_level','5']
    elif encoding.get('codec')=='opus':codec=['-c:a','libopus','-b:a',str(int(encoding.get('bitrate_kbps',128)))+'k']
    else:raise ValueError('Unsupported archive codec')
    run(['ffmpeg','-y','-v','error','-i',str(source),'-af',filt,'-ar','48000','-ac','2',*codec,'-metadata','comment=Ambient Music Nonstop | AI generated',str(destination)])
    final = inspect(destination,length)
    lm = loudness(destination)
    final.update(lufs=float(lm['input_i']),true_peak_db=float(lm['input_tp']),lra=float(lm['input_lra']))
    if abs(final['lufs']-target_i)>.7 or final['true_peak_db']>-.7:
        raise Rejection(f'final_loudness_out_of_range: {final}')
    final['sha256'] = hashlib.sha256(Path(destination).read_bytes()).hexdigest()
    edited.unlink(missing_ok=True)
    return {'raw':raw,'final':final,'edge_edit':{'head_seconds':head,'tail_seconds':tail,'maximum_per_edge':3,
            'method':'musical intro and decay preserved' if preserve_edges else 'stereo RMS; below 28% of middle median; 120 ms sustain; 60 ms safety margin',
            'microfade_seconds':.025},'encoding':encoding,
            'normalizer':'FFmpeg measured static gain; dynamics preserved' if preserve else 'FFmpeg two-pass loudnorm -18 LUFS / -1.5 dBTP',
            'loudness_target':target_i,'gain_db':gain,'peak_limited':bool(preserve and target_i < -18.01),'qc_version':4}
