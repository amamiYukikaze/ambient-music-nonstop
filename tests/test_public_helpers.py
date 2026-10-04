import subprocess
import sys
from pathlib import Path


def test_audition_requires_explicit_paths_before_importing_models():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'scripts/sa3_audition.py')],
                            capture_output=True, timeout=15)
    assert result.returncode == 2
    for required in (b'--model-dir', b'--prompts', b'--output'):
        assert required in result.stderr
    assert b'Traceback' not in result.stderr
