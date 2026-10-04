"""Disposable desktop fixtures; the player files are synthetic tones, not QC evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--mode',choices=['fresh','player','corrupt','partial'],required=True)
args=parser.parse_args()
root=Path(tempfile.mkdtemp(prefix='ambient-desktop-'+args.mode+' '))
os.environ['AMBIENT_DATA_DIR']=str(root);os.environ['AMBIENT_NO_WORKER']='1'
sys.path.insert(0,str(args.runtime.resolve()))
from server import database as db,preferences as prefs
db.initialize()
if args.mode=='player':
    for n in (1,2):
        ident=str(n)*32;file=root/'MusicLib/lofi'/(ident+'.opus');file.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(args.runtime/'tools/ffmpeg/bin/ffmpeg.exe'),'-nostdin','-v','error','-f','lavfi','-i',f'sine=frequency={220*n}:sample_rate=48000','-t','60','-c:a','libopus','-b:a','96k',str(file)],check=True)
        metadata={'fixture':True,'model':'Synthetic test fixture','bpm_requested':120,'timesignature_requested':'4','qc':{'edge_edit':{},'final':{'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'lufs':-21.1,'true_peak':-18.0}}}
        with db.connection() as connection:
            connection.execute('INSERT INTO tracks(id,style,title,path,duration,bytes,status,created,metadata) VALUES(?,?,?,?,?,?,?,?,?)',
                               (ident,'lofi','Synthetic desktop test',str(file),60,file.stat().st_size,'ready',db.now(),json.dumps(metadata)))
    config=prefs.read_config();config['setup'].update(complete=True,legacy_adopted=True);prefs.write_config(config)
prefs.save_settings({'auto_generate':False})
if args.mode=='corrupt':(root/'config.json').write_text('{incomplete',encoding='utf8')
if args.mode=='partial':(root/'config.json').write_text('{"version":2,"settings":{"duration":180}}',encoding='utf8')
print(root)
