"""Support both a Git checkout and a pinned release source archive."""
import subprocess
from pathlib import Path
def revision(directory):
    directory=Path(directory);marker=directory/'.source-revision'
    if (directory/'.git').exists():return subprocess.check_output(['git','-C',str(directory),'rev-parse','HEAD'],text=True).strip()
    return marker.read_text(encoding='ascii').strip()
