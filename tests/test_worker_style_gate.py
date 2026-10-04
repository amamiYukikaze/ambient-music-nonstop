"""Revision tags must never bypass the real QC worker's semantic gate."""
import json
import runpy
import sys
import types
from pathlib import Path
import numpy as np
import pytest

@pytest.mark.parametrize('revision',['2026-09-24-distinct-v5','2026-09-24-sft-evaluation-v5','future-prompt'])
def test_qc_worker_rejects_lofi_in_guitar_regardless_of_revision(tmp_path,monkeypatch,revision):
    from server import qc,embedding
    root=Path(__file__).resolve().parents[1]
    with np.load(root/'server/style_reference_v5.npz',allow_pickle=False) as bank:
        vector=bank['text_vectors'][bank['text_labels'].tolist().index('lofi')].copy()
    request=tmp_path/'request.json'
    request.write_text(json.dumps({'output':str(tmp_path),'source':'stub.wav','duration':180,'style':'guitar','prompt_revision':revision}))
    monkeypatch.setattr(qc,'normalize',lambda *args:{})
    monkeypatch.setattr(embedding,'features',lambda *args:(vector,np.zeros((12,64)),{}))
    monkeypatch.setitem(sys.modules,'worker_watchdog',types.SimpleNamespace(start=lambda:None))
    monkeypatch.setattr(sys,'argv',['qc_worker.py',str(request)])
    with pytest.raises(SystemExit) as stopped:runpy.run_path(str(root/'scripts/qc_worker.py'),run_name='__main__')
    assert stopped.value.code==1
    result=json.loads((tmp_path/'qc-result.json').read_text(encoding='utf8'))
    assert result['error_code']=='qc_rejection' and 'style_mismatch' in result['error']
    assert not (tmp_path/'embedding.bin').exists()


