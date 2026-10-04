"""Local health cache, invalidated by runtime files, verifier, locks and GPU driver.

This is a performance cache, not a tamper-proof signature. Unchanged files use
Windows directory metadata; installation and cache misses still run real probes.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

CACHE_VERSION = 1
CACHE_NAME = '.runtime-health-cache.json'


def file_hash(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(root, spec_path):
    spec = json.loads(spec_path.read_text(encoding='utf8'))
    receipt = json.loads((root / 'runtime.json').read_text(encoding='utf8'))
    if (receipt.get('schema_version') != 1 or receipt.get('spec_sha256') != file_hash(spec_path)
            or receipt.get('runtime_version') != spec['runtime_version']):
        raise ValueError('Runtime metadata is outdated; repair is required')
    controls = [root / 'runtime.json', spec_path, Path(__file__),
                Path(__file__).with_name('runtime_health.py')]
    controls += [root / 'scripts' / name for name in spec['lock_sha256']]
    return {'version': CACHE_VERSION, 'root': str(root.resolve()),
            'platform': [platform.system(), platform.machine(), platform.version()],
            'controls': [file_hash(file) for file in controls]}


def inventory(root, progress=lambda event: None):
    digest = hashlib.sha256()
    count = 0
    last_report = time.monotonic()

    def visit(folder, prefix):
        nonlocal count, last_report
        with os.scandir(folder) as stream:
            entries = sorted(stream, key=lambda entry: entry.name)
        for entry in entries:
            if entry.name in ('__pycache__', '.git') or entry.name.endswith(('.pyc', '.pyo')):
                continue
            if entry.is_symlink():
                raise ValueError('Linked runtime files require full validation')
            if entry.is_dir(follow_symlinks=False):
                visit(entry.path, prefix + entry.name + '/')
            else:
                stat = entry.stat(follow_symlinks=False)
                relative = prefix + entry.name
                digest.update(json.dumps([relative, stat.st_size, stat.st_mtime_ns,
                                          stat.st_ctime_ns], ensure_ascii=True).encode())
                count += 1
            if time.monotonic() - last_report > .2:
                progress({'phase': 'inventory', 'files': count})
                last_report = time.monotonic()

    for name in ('vendor', '.venv-sa3-py311', 'tools'):
        visit(root / name, name + '/')
    return {'digest': digest.hexdigest(), 'files': count}


def driver_identity():
    result = subprocess.run(['nvidia-smi', '--query-gpu=uuid,driver_version',
                             '--format=csv,noheader'], capture_output=True, text=True,
                            timeout=8, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if not result.stdout.strip():
        raise ValueError('No NVIDIA GPU detected')
    return result.stdout.strip()


def snapshot(root, spec_path, progress=lambda event: None):
    progress({'phase': 'metadata'})
    key = identity(root, spec_path)
    progress({'phase': 'inventory', 'files': 0})
    files = inventory(root, progress)
    progress({'phase': 'driver', 'files': files['files']})
    return {'identity': key, 'inventory': files, 'driver': driver_identity()}


def save(root, value):
    # A replace is atomic; an interrupted writer never leaves a partially valid cache.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=root,
                                     prefix='.runtime-health-', suffix='.part', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(root / CACHE_NAME)
    finally:
        temporary.unlink(missing_ok=True)


def startup_check(root, spec_path, full_check, progress=lambda event: None):
    if (root / '.runtime-installing').exists():
        return {'ok': False, 'errors': ['Incomplete runtime installation; repair is required']}
    started = time.monotonic()
    before = None
    try:
        before = snapshot(root, spec_path, progress)
        cached = json.loads((root / CACHE_NAME).read_text(encoding='utf8'))
        if cached == before:
            return {'ok': True, 'errors': [], 'mode': 'cached',
                    'files': before['inventory']['files'],
                    'seconds': round(time.monotonic() - started, 3)}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass
    progress({'phase': 'deep', 'reason': 'cache-miss'})
    result = full_check()
    result['mode'] = 'full'
    if result['ok']:
        try:
            after = snapshot(root, spec_path, progress)
            # Detect files changing during the probes. Never bless such a snapshot.
            if before is not None and after != before:
                return {'ok': False, 'errors': ['Runtime changed during validation; close other installers and retry.']}
            save(root, after)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            result['cache_warning'] = str(exc)
    result['seconds'] = round(time.monotonic() - started, 3)
    return result
