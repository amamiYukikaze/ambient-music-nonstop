"""Re-acquire the published CC BY 4.0 preview and rebuild only the thunder layer."""
import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE = 'https://freesound.org/people/digifishmusic/sounds/41739/'
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
PROCESSING = ('Official HQ MP3 preview repeated to 62 seconds; 12 kHz lowpass; '
              '2 second linear seam crossfade; normalized to -24 LUFS, -3 dBTP; '
              '48 kHz stereo Opus at 96 kbps, 60 second loop.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new file for review')
    with urllib.request.urlopen(SOURCE, timeout=45) as response:
        page = response.read()
    html = page.decode('utf8')
    if f'href="{LICENSE}"' not in html:
        raise ValueError('Current source page does not confirm CC BY 4.0; verify manually')
    preview = re.search(r'https://cdn\.freesound\.org/previews/41/41739_\d+-hq\.mp3', html)
    if not preview:
        raise ValueError('Source preview URL unavailable; verify manually')
    with urllib.request.urlopen(preview.group(), timeout=90) as response:
        audio = response.read()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    source = args.evidence_dir / '41739-hq.mp3'
    source.write_bytes(audio)
    (args.evidence_dir / 'source-page.html').write_bytes(page)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    filters = ['[0:a]atrim=0:62,asetpts=PTS-STARTPTS,lowpass=f=12000,asplit=3[h][m][t]',
               '[h]atrim=0:2,asetpts=PTS-STARTPTS[head]',
               '[m]atrim=2:60,asetpts=PTS-STARTPTS[mid]',
               '[t]atrim=60:62,asetpts=PTS-STARTPTS[tail]',
               '[tail][head]acrossfade=d=2:c1=tri:c2=tri[seam]',
               '[seam][mid]concat=n=2:v=0:a=1,loudnorm=I=-24:TP=-3:LRA=10[out]']
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-stream_loop', '-1', '-i', str(source),
               '-filter_complex', ';'.join(filters), '-map', '[out]', '-map_metadata', '-1',
               '-ar', '48000', '-ac', '2', '-c:a', 'libopus', '-b:a', '96k', str(args.output)]
    subprocess.run(command, check=True, timeout=180)
    report = {'acquired_at': datetime.now(timezone.utc).isoformat(), 'source_url': SOURCE,
              'license_url': LICENSE, 'download_url': preview.group(),
              'source_sha256': hashlib.sha256(audio).hexdigest(),
              'source_page_sha256': hashlib.sha256(page).hexdigest(),
              'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'processing': PROCESSING}
    (args.evidence_dir / 'acquisition.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
