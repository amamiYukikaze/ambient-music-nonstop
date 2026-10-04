"""Conservative semantic drift gate, not proof of instrumentation or genre."""
from pathlib import Path
import numpy as np
from .qc import Rejection

# Calibrated against local reference excerpts; CLAP confuses related acoustic timbres.
LIMITS={'guitar':(.46,.05),'artcore':(.28,.02),
        'daily_piano':(.40,.03),'anime_daily':(.43,.035),'orchestral':(.38,.02)}

def inspect_style(vector,style):
    if style not in LIMITS:return None
    with np.load(Path(__file__).with_name('style_reference_v5.npz'),allow_pickle=False) as bank:
        labels=bank['text_labels'].tolist()
        scores=dict(zip(labels,map(float,bank['text_vectors']@vector)))
        reference=float(bank[style]@vector) if style in bank else None
    target,margin=LIMITS[style]
    report={'version':5,'text_scores':scores,'reference_cosine':reference,
            'lofi_margin':scores[style]-scores['lofi'],'minimum_target':target,'minimum_margin':margin,
            'limitation':'Semantic screening only; not an instrument separation, tempo or human listening verdict.'}
    report['passed']=scores[style]>=target and report['lofi_margin']>=margin
    return report

def require_style(report):
    if report and not report['passed']:
        raise Rejection(f'style_mismatch: target/lofi margin {report["lofi_margin"]:.3f}, required {report["minimum_margin"]:.3f}; scores={report["text_scores"]}')
