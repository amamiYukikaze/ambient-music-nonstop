"""Isolate CPU embeddings from inference RAM, return compact measured metadata."""
import json
import sys
from pathlib import Path
from worker_watchdog import start as start_watchdog
start_watchdog()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.qc import normalize, Rejection
from server.embedding import features
from server.style_qc import inspect_style, require_style
from server.tonality import inspect_tonality, require_tonality
request=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
out=Path(request['output'])
metrics=None
meta=None
try:
    from server.preferences import load_worker_config
    load_worker_config()
    encoding=request.get('encoding',{'codec':'opus','bitrate_kbps':128})
    archive_file='normalized.flac' if encoding.get('codec')=='flac' else 'normalized.opus'
    metrics=normalize(request['source'],out/archive_file,request['duration'],encoding)
    vector,signature,meta=features(out/archive_file)
    # Gate by musical category, never by a human-readable prompt revision tag.
    style_report=inspect_style(vector,request['style'])
    meta['style_screen']=style_report
    (out/'style-report.json').write_text(json.dumps(style_report,indent=2),encoding='utf8')
    require_style(style_report)
    if request.get('tonal_policy')=='major-v6':
        report=inspect_tonality(out/archive_file,request['key'])
        meta['tonality']=report
        (out/'tonality-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        require_tonality(report)
    vector.tofile(out/'embedding.bin')
    signature.tofile(out/'fingerprint.bin')
    result=dict(success=True,qc=metrics,analysis=meta,archive_file=archive_file)
except Exception as exc:
    result=dict(success=False,error_code='qc_rejection' if isinstance(exc,Rejection) else 'audio_processing_error',error=str(exc))
    # Preserve completed measurements in the job log even when a later gate
    # rejects the candidate and the staging files are subsequently cleaned.
    if metrics is not None:result['qc']=metrics
    if meta is not None:result['analysis']=meta
(out/'qc-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(0 if result['success'] else 1)
