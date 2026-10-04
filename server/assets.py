"""User imports are copied into owned storage; shipped assets are immutable."""
import json
import math
import uuid
from functools import lru_cache
from pathlib import Path
from .config import DATA
from .preferences import read_config,update_config,lock

MAX_AMBIENCE_SECONDS=180
DECODE_SAMPLE_RATE=24000

class AmbienceLimitError(ValueError):pass

def ambience_items():
    p=DATA/'Ambience/manifest.json'
    return (json.loads(p.read_text(encoding='utf8')) if p.exists() else [])+read_config().get('ambience',[])

def import_asset(kind,source,name,icon='♪',environment='city',period='any',styles=None,focus=None):
    cfg=read_config();src=Path(source).resolve()
    if kind not in ('images','ambience'):raise ValueError('未知素材类型')
    if not src.is_file() or src.stat().st_size>250*1024**2:raise ValueError('请选择不超过 250 MB 的本地文件')
    if not name.strip() or len(name)>80 or len(icon)>12:raise ValueError('名称应为 1–80 字，Logo 不超过 12 字符')
    from .config import STYLE_MAP
    styles=styles or []
    if any(s not in STYLE_MAP for s in styles):raise ValueError('未知曲风关联')
    if environment not in ('city','ocean','forest','fireplace','stream','snow','train','any') or period not in ('day','night','twilight','any'):raise ValueError('未知场景或时间')
    focus=focus or [.5,.5]
    if len(focus)!=2 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in focus):raise ValueError('裁切焦点应为 0–1')
    ident='custom_'+uuid.uuid4().hex;directory=Path(cfg['paths'][kind]).resolve();directory.mkdir(parents=True,exist_ok=True)
    item={'id':ident,'name':name.strip(),'custom':True}
    dest=directory/(ident+('.webp' if kind=='images' else '.opus'))
    try:
        if kind=='images':
            from PIL import Image,ImageOps
            with Image.open(src) as image:
                if image.width*image.height>60_000_000:raise ValueError('图片超过 6000 万像素')
                image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((3840,2160))
                image.save(dest,format='WEBP',quality=92)
            item.update(path=str(dest),environment=environment,period=period,styles=styles,focus=focus)
        else:
            from .qc import probe,run
            info=probe(src)
            if not 2<=info['duration']<=MAX_AMBIENCE_SECONDS:raise ValueError('环境声长度应为 2 秒至 3 分钟；请先裁剪长录音')
            run(['ffmpeg','-nostdin','-v','error','-i',str(src),'-vn','-af','loudnorm=I=-24:TP=-2:LRA=11','-ar',str(DECODE_SAMPLE_RATE),'-ac','2','-c:a','libopus','-b:a','160k','-y',str(dest)])
            item.update(path=str(dest),icon=icon,duration=info['duration'],sources=[])
        # Conversion can overlap; commit against the latest index under the config lock.
        with lock:
            latest=read_config();latest[kind].append(item);update_config(**{kind:latest[kind]})
    except Exception:
        dest.unlink(missing_ok=True);raise
    return item

def ambience_path(ident):
    if ident.startswith('custom_'):return media_path('ambience',ident)
    item=next((x for x in ambience_items() if x['id']==ident and not x.get('custom')),None)
    if not item:raise ValueError('找不到环境声')
    from .config import safe_path
    path=safe_path(DATA/'Ambience'/item['file'],'Ambience')
    if not path.is_file():raise ValueError('环境声文件已丢失，请重启应用修复')
    return path

@lru_cache(maxsize=64)
def _ambience_info(path,modified,size):
    from .qc import probe
    if size>8*1024**2:raise AmbienceLimitError('此环境声过大，请裁剪为 3 分钟以内并重新导入')
    info=probe(Path(path))
    if not math.isfinite(info['duration']) or not 0<info['duration']<=MAX_AMBIENCE_SECONDS+.25 or not 1<=info['channels']<=2:
        raise AmbienceLimitError('此环境声超过 3 分钟或双声道限制，请裁剪后重新导入')
    return {**info,'decode_sample_rate':DECODE_SAMPLE_RATE,
            'decoded_bytes':math.ceil((info['duration']+.25)*DECODE_SAMPLE_RATE)*2*4}

def ambience_info(ident):
    path=ambience_path(ident);stat=path.stat()
    return dict(_ambience_info(str(path),stat.st_mtime_ns,stat.st_size))

def media_path(kind,ident):
    item=next((x for x in read_config().get(kind,[]) if x['id']==ident),None)
    if not item:raise ValueError('找不到素材')
    path=Path(item['path']).resolve()
    if not path.is_file():raise ValueError('素材文件已移动或丢失')
    return path
