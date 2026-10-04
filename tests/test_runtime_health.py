"""A present executable or package is insufficient to declare a runtime healthy."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/runtime_health.py'


def module():
    spec = importlib.util.spec_from_file_location('runtime_health', SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_real_import_and_version_failures_are_reported():
    health = module()
    valid = {'python': '.'.join(map(str, sys.version_info[:3])),
             'imports': ['json'], 'packages': {}, 'cuda': False}
    assert health.probe_environment(valid)['ok']
    broken = {**valid, 'imports': ['ambient_deliberately_missing_dependency']}
    assert not health.probe_environment(broken)['ok']
    assert not health.probe_environment({**valid, 'python': '0.0.0'})['ok']
    assert not health.probe_environment({**valid, 'packages': {'pip': '0.0.0'}})['ok']


def test_source_snapshot_detects_missing_or_modified_file(tmp_path):
    import hashlib
    import json
    health = module()
    source = tmp_path / 'source'; source.mkdir()
    code = source / 'engine.py'; code.write_bytes(b'original')
    (source / '.source-revision').write_text('abc')
    (source / '.source-manifest.json').write_text(json.dumps([
        {'path': 'engine.py', 'sha256': hashlib.sha256(b'original').hexdigest()}]))
    health.verify_source(source, 'abc')
    code.write_bytes(b'corrupt')
    import pytest
    with pytest.raises(ValueError, match='snapshot'):
        health.verify_source(source, 'abc')
    code.unlink()
    with pytest.raises(ValueError, match='snapshot'):
        health.verify_source(source, 'abc')
