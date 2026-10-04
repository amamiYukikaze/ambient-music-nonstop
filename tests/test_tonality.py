import numpy as np
import pytest
from server.tonality import condition,summarize,MAJOR,MINOR,MAJOR_KEYS,require_tonality
from server.qc import Rejection

def test_condition_rejects_minor_and_spellings():
    for key in MAJOR_KEYS:
        assert key in condition('solo piano',key)
    with pytest.raises(ValueError):condition('piano','A Minor')

def test_major_minor_screen_transposes_and_is_not_probability():
    for tonic in range(12):
        major=summarize(np.tile(np.roll(MAJOR,tonic)[:,None],(1,120)),'C Major')
        minor=summarize(np.tile(np.roll(MINOR,tonic)[:,None],(1,120)),'C Major')
        assert major['estimated_key'].endswith('Major') and not major['rejected']
        assert minor['estimated_key'].endswith('Minor') and minor['reason']=='strong_minor_evidence'
        with pytest.raises(Rejection):require_tonality(minor)



