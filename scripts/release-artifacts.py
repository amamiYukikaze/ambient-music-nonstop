"""Create deterministic ZIPs from audited trees and verify every stored byte."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def make_zip(root,files,destination):
    entries=[]
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for relative in sorted(files):
            file=root/relative
            info=zipfile.ZipInfo(root.name+'/'+relative,date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            with file.open('rb') as source,archive.open(info,'w',force_zip64=True) as output:
                while block:=source.read(1024*1024):output.write(block)
            entries.append({'path':relative,'bytes':file.stat().st_size,'sha256':digest(file)})
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP integrity failure')
        for entry in entries:
            with archive.open(root.name+'/'+entry['path']) as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=entry['sha256']:raise ValueError('ZIP content mismatch')
    return entries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve();package=args.package.resolve();out=args.output.resolve()
    if out.exists():raise ValueError('Use a new artifact directory; previous releases are never overwritten')
    manifest=json.loads((source/'public-source-manifest.json').read_text())
    version=json.loads((source/'package.json').read_text())['version']
    for entry in manifest['files']:
        if digest(source/entry['path'])!=entry['sha256']:raise ValueError('Source changed after its audit')
    out.mkdir(parents=True)
    source_zip=out/f'Ambient-Music-Nonstop-{version}-source.zip'
    package_zip=out/f'Ambient-Music-Nonstop-{version}-win32-x64.zip'
    source_entries=make_zip(source,[e['path'] for e in manifest['files']]+['public-source-manifest.json'],source_zip)
    package_entries=make_zip(package,[p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()],package_zip)
    report=out/'release-content-manifest.json'
    report.write_text(json.dumps({'version':version,'source':source_entries,'windows':package_entries},indent=2)+'\n',encoding='utf8',newline='\n')
    artifacts=[source_zip,package_zip,report]
    checksums=out/'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{digest(p)}  {p.name}\n' for p in artifacts),encoding='ascii',newline='\n')
    print(json.dumps({'version':version,'source_files':len(source_entries),'package_files':len(package_entries),'artifacts':[str(p) for p in artifacts+[checksums]]},indent=2))


if __name__=='__main__':main()
