"""Repair only manifest-owned builtins, preserving replaced bytes for recovery."""
import hashlib
import json
import os
import re
import uuid
from .paths import reject_links


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def atomic_copy(source,target):
    reject_links(target)
    temporary=target.with_name(target.name+'.part-'+uuid.uuid4().hex)
    try:
        with source.open('rb') as inp,temporary.open('wb') as out:
            while block:=inp.read(1024*1024):out.write(block)
            out.flush();os.fsync(out.fileno())
        if digest(temporary)!=digest(source):raise OSError('Builtin copy checksum mismatch')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def preserve(path,directory):
    if not path.exists():return
    reject_links(path);reject_links(directory)
    directory.mkdir(exist_ok=True)
    backup=directory/(path.name+'-'+digest(path))
    if not backup.exists():atomic_copy(path,backup)


def repair_builtins(source,destination):
    manifest=source/'manifest.json'
    if not manifest.is_file():raise ValueError('Packaged builtin ambience manifest is missing')
    entries=json.loads(manifest.read_text(encoding='utf8'))
    if not isinstance(entries,list):raise ValueError('Invalid builtin manifest')
    names=set()
    # Validate every packaged source before changing any installed file.
    for entry in entries:
        name=entry.get('file','');ident=entry.get('id','')
        if not re.fullmatch('[a-z][a-z0-9_-]*',ident) or name!=ident+'.opus' or name in names:
            raise ValueError('Invalid builtin filename')
        names.add(name)
        reject_links(source/name)
        if not (source/name).is_file() or digest(source/name)!=entry.get('sha256'):
            raise ValueError('Packaged builtin checksum mismatch: '+name)
    reject_links(destination);destination.mkdir(parents=True,exist_ok=True)
    recovery=destination/'.recovery'
    for entry in entries:
        target=destination/entry['file'];reject_links(target)
        if target.is_file() and digest(target)==entry['sha256']:continue
        preserve(target,recovery)
        atomic_copy(source/entry['file'],target)
    target=destination/'manifest.json';reject_links(target)
    if not target.is_file() or target.read_bytes()!=manifest.read_bytes():
        preserve(target,recovery)
        atomic_copy(manifest,target)
