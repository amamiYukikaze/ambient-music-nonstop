"""Shared, read-only runtime probe. Installation commits a receipt only after it passes."""
import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe_environment(expected):
    errors, timings = [], {}
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1',GRADIO_ANALYTICS_ENABLED='False',TOKENIZERS_PARALLELISM='false')
    actual = platform.python_version()
    if actual != expected['python']:
        errors.append(f"Python {actual}; expected {expected['python']}")
    for name, version in expected['packages'].items():
        try:
            if importlib.metadata.version(name) != version:
                errors.append(f'{name}: version mismatch (expected {version})')
        except importlib.metadata.PackageNotFoundError:
            errors.append(f'{name}: dependency missing')
    for name in expected['imports']:
        started=time.monotonic()
        try:
            with contextlib.redirect_stdout(sys.stderr):
                importlib.import_module(name)
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
        timings[name]=round(time.monotonic()-started,2)
    if expected.get('cuda'):
        try:
            import torch
            if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
                raise RuntimeError('NVIDIA CUDA device 0 is unavailable')
            # Exercise driver/DLL loading and an actual allocation, without loading weights.
            value = torch.ones(1, device='cuda:0')
            if value.cpu().item() != 1:
                raise RuntimeError('CUDA device 0 computation failed')
            del value
        except Exception as exc:
            errors.append(f'CUDA device 0: {exc}')
    return {'ok': not errors, 'python': actual, 'errors': errors, 'import_seconds':timings}


def verify_source(directory, revision):
    try:
        if (directory / '.source-revision').read_text(encoding='ascii').strip() != revision:
            raise ValueError('revision mismatch')
        manifest = json.loads((directory / '.source-manifest.json').read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, list) or not manifest:
            raise ValueError('empty source manifest')
        for entry in manifest:
            target = (directory / entry['path']).resolve()
            if not target.is_relative_to(directory.resolve()) or sha256(target) != entry['sha256']:
                raise ValueError(entry['path'])
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ValueError(f'Source snapshot needs repair: {directory.name}: {exc}') from exc


def command(args, root, timeout=90, json_probe=False):
    process = subprocess.Popen([str(x) for x in args], cwd=root, stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               encoding='utf8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # The Windows venv executable launches another Python; kill the owned tree.
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        else:process.kill()
        process.communicate(timeout=10)
        raise RuntimeError('Runtime check timed out') from exc
    if process.returncode and not (json_probe and stdout.strip()):
        raise RuntimeError((stderr or stdout)[-2500:])
    return stdout


def environment_spec(spec, name, scripts):
    expected = {**spec['environments'][name], 'python': spec['python']}
    expected['packages'] = dict(expected['packages'])
    lock = scripts / expected['lock']
    if sha256(lock) != spec['lock_sha256'][lock.name]:
        raise ValueError(f'Runtime dependency lock changed: {lock.name}')
    for package, version in re.findall(r'^([a-zA-Z0-9_.-]+)==([^\s\\]+)', lock.read_text(), re.M):
        expected['packages'][package] = version
    return expected


def check_runtime(root, spec_path, managed=True, complete_install=False):
    errors, checks, manifests = [], {}, {}
    spec = json.loads(spec_path.read_text(encoding='utf8'))
    spec_hash = sha256(spec_path)
    scripts = root / 'scripts'
    if spec.get('schema_version') != 1 or platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        errors.append('Runtime requires Windows x64 and a supported runtime specification')
    if not complete_install and (root / '.runtime-installing').exists():
        errors.append('Incomplete runtime installation; repair is required')
    if managed and not complete_install:
        try:
            receipt = json.loads((root / 'runtime.json').read_text(encoding='utf8'))
            if receipt['schema_version'] != 1 or receipt['spec_sha256'] != spec_hash or receipt['runtime_version'] != spec['runtime_version']:
                errors.append('Runtime metadata is outdated; repair is required')
        except (OSError, ValueError, KeyError, TypeError):
            errors.append('Runtime metadata is missing or invalid; repair is required')
            receipt = {}
    else:
        receipt = {}
    if errors and not complete_install:
        return {'ok':False,'errors':errors,'checks':checks}
    for name, source in spec['sources'].items():
        try:
            directory = root / source['folder']
            if managed:
                verify_source(directory, source['revision'])
                manifests[name] = sha256(directory / '.source-manifest.json')
                if receipt and receipt.get('source_manifests', {}).get(name) != manifests[name]:
                    raise ValueError('Source manifest changed since installation')
            else:
                from source_revision import revision
                if revision(directory) != source['revision']:
                    raise ValueError('Source revision mismatch')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    if errors and not complete_install:
        return {'ok':False,'errors':errors,'checks':checks}
    for name, environment in spec['environments'].items():
        try:
            environment_spec(spec, name, scripts)
            python = root / environment['executable']
            result = json.loads(command([python, scripts / 'runtime_health.py', '--root', root,
                                         '--spec', spec_path, '--probe', name], root, timeout=120,json_probe=True))
            checks[name] = result
            errors.extend(f'{name}: {message}' for message in result['errors'])
        except Exception as exc:
            errors.append(f'{name} Python runtime: {exc}')
    for name in ('ffmpeg', 'ffprobe'):
        try:
            binary = root / f'tools/ffmpeg/bin/{name}.exe'
            if not managed and not binary.is_file():
                binary = Path(shutil.which(name) or str(binary))
            if managed and sha256(binary) != spec['ffmpeg']['executables'][name]:
                raise ValueError('Pinned executable checksum mismatch')
            line = command([binary, '-version'], root).splitlines()[0]
            expected = spec['ffmpeg']['version'] if managed else spec['ffmpeg']['version'].split('.')[0] + '.'
            if not line.startswith(f'{name} version {expected}'):
                raise ValueError('Unexpected FFmpeg version')
            checks[name] = line
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    if managed:
        try:
            uv = root / 'tools/uv/uv.exe'
            if sha256(uv) != spec['uv']['executable_sha256']:
                raise ValueError('Pinned uv checksum mismatch')
            if not command([uv, '--version'], root).startswith('uv ' + spec['uv']['version'] + ' '):
                raise ValueError('Unexpected uv version')
            for environment in spec['environments'].values():
                command([uv, 'pip', 'check', '--python', root / environment['executable']], root)
        except Exception as exc:
            errors.append(f'Dependency integrity: {exc}')
    result = {'ok': not errors, 'errors': errors, 'checks': checks}
    if complete_install and result['ok']:
        payload = {'schema_version': 1, 'runtime_version': spec['runtime_version'],
                   'spec_sha256': spec_hash, 'source_manifests': manifests, 'checks': checks}
        temporary = root / 'runtime.json.part'
        with temporary.open('w', encoding='utf8', newline='\n') as out:
            json.dump(payload, out, indent=2)
            out.flush(); os.fsync(out.fileno())
        temporary.replace(root / 'runtime.json')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--probe', choices=['base', 'sa3'])
    parser.add_argument('--development', action='store_true')
    parser.add_argument('--complete-install', action='store_true')
    args = parser.parse_args()
    try:
        if args.probe:
            spec = json.loads(args.spec.read_text(encoding='utf8'))
            result = probe_environment(environment_spec(spec, args.probe, args.root / 'scripts'))
        else:
            result = check_runtime(args.root.resolve(), args.spec.resolve(),
                                   not args.development, args.complete_install)
    except Exception as exc:
        result = {'ok': False, 'errors': [str(exc)]}
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
