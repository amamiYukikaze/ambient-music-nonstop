"""Major conditioning and conservative tonal diagnostics, not note transcription."""
import numpy as np
from .qc import Rejection, decode

MAJOR_KEYS = ('C Major', 'D Major', 'F Major', 'G Major', 'A Major')
NOTES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

def condition(prompt, key):
    if key not in MAJOR_KEYS:raise ValueError('Only configured major keys are allowed for new music')
    return (f'Entirely in {key}, bright major-key harmony throughout, warm contentment and quiet optimism. '
            'Stable major tonic, affirmative phrase endings; no minor-key sections or melancholy mood. '+prompt)


def summarize(chroma, key):
    """Profile correlation is a score, never a calibrated probability."""
    chroma=np.maximum(np.asarray(chroma,dtype=float),0)
    if chroma.ndim!=2 or chroma.shape[0]!=12 or not np.isfinite(chroma).all():
        raise ValueError('Invalid chroma')
    templates=np.stack([np.roll(p,t) for p in (MAJOR,MINOR) for t in range(12)])
    templates-=templates.mean(axis=1,keepdims=True)
    templates/=np.linalg.norm(templates,axis=1,keepdims=True)
    def score(v):
        v=v-v.mean();return templates @ (v/max(np.linalg.norm(v),1e-9))
    scores=score(chroma.mean(axis=1));major=int(np.argmax(scores[:12]));minor=12+int(np.argmax(scores[12:]))
    best=int(np.argmax(scores));margin=float(scores[minor]-scores[major])
    windows=[score(c.mean(axis=1)) for c in np.array_split(chroma,min(12,chroma.shape[1]),axis=1)]
    minor_share=float(np.mean([s[12:].max()-s[:12].max()>.08 for s in windows]))
    reject_minor=bool(scores[minor]>.65 and margin>.12 and minor_share>=.65)
    return dict(method_version=3,method='harmonic CQT / Krumhansl-Schmuckler profile correlation',
        estimated_key=f'{NOTES[best%12]} {"Major" if best<12 else "Minor"}' if scores[best]>=.5 else 'Undetermined',
        requested_key=key,score=float(scores[best]),minor_over_major_margin=margin,
        minor_window_fraction=minor_share,
        rejected=reject_minor,reason='strong_minor_evidence' if reject_minor else None,
        note='Heuristic screening, not verified transcription or mood judgment. Relative modes, ornaments and overtones are ambiguous; listening review remains required.')

def inspect_tonality(path, key):
    import librosa
    mono=decode(path,12000,channels=1).ravel().copy()
    harmonic=librosa.effects.harmonic(mono,margin=3)
    chroma=librosa.feature.chroma_cqt(y=harmonic,sr=12000,hop_length=1024,n_octaves=6)
    return summarize(chroma,key)

def require_tonality(report):
    if report['rejected']:raise Rejection(f'tonality_mismatch: {report["reason"]}; estimate={report["estimated_key"]}')
