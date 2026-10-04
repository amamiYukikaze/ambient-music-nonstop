"""Paths and conservative defaults. No secrets in configuration files."""
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
_legacy = Path('D:/AmbMusicNonstop')
DATA = Path(os.environ.get('AMBIENT_DATA_DIR') or (_legacy if (_legacy/'library.sqlite3').exists() else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'AmbientMusicNonstop/data')).resolve()
CONFIG_FILE = DATA/'config.json'
STYLES = json.loads((PROJECT / 'server/styles.json').read_text(encoding='utf8'))
# User JSON is validated during database startup, never during module import.
STYLE_MAP = {s['id']: s for s in STYLES}
PYTHON = PROJECT / 'vendor/ACE-Step-1.5/.venv/Scripts/python.exe'
SA3_PYTHON = PROJECT / '.venv-sa3-py311/Scripts/python.exe'
DEFAULTS = {'auto_generate': True, 'enabled_styles': list(STYLE_MAP), 'capacity_gb': 10,
            'style_pins': [],
            'style_weights': {s['id']:s['weight'] for s in STYLES}, 'library_path':str(DATA/'MusicLib'),
            'duration': 180, 'crossfade': 6, 'plays_before_retire': 4,
            'minimum_free_gb': 20, 'generation_interval': 30,
            'vram_gb': 6.5, 'target_lufs': -18.0, 'true_peak': -1.5}

def model_root(kind):
    from .preferences import read_config
    return Path(read_config().get('paths',{}).get('models',str(DATA/'models')))/kind


def setup_dirs():
    for name in ['.log', 'staging', 'models', 'Ambience']:
        (DATA / name).mkdir(parents=True, exist_ok=True)


def library_root():
    from .database import settings
    return Path(settings().get('library_path',str(DATA/'MusicLib'))).resolve()


def safe_path(path, subdir='MusicLib'):
    """Only resolve files strictly under our owned media directory."""
    p = Path(path).resolve()
    base = library_root() if subdir=='MusicLib' else (DATA / subdir).resolve()
    if not p.is_relative_to(base) or p == base:
        raise ValueError('Path outside owned directory')
    return p
