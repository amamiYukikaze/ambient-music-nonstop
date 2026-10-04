"""Consent-based device check and resumable, pinned Hugging Face downloads."""
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from .config import DATA,model_root,STYLE_MAP
from .preferences import read_config,update_config,save_settings
from .operation_lock import exclusive

CATALOG={
 'acestep-v15-turbo':('ACE-Step/Ace-Step1.5','19671f406d603126926c1b7e2adc169acbcade22','ace-step/checkpoints',['acestep-v15-turbo/*','Qwen3-Embedding-0.6B/*','vae/*']),
 'acestep-v15-sft':('ACE-Step/acestep-v15-sft','c410d249e71ea9385a7b586865e65b1473e1098d','ace-step/checkpoints/acestep-v15-sft',['*']),
 'stable-audio-3-medium':('stabilityai/stable-audio-3-medium','27b5a21b791b1b033d193a9e1e3ce78493f102f9','stable-audio-3-medium',['model_config.json','model.safetensors','t5gemma-b-b-ul2/*','LICENSE*','README.md']),
 'clap':('laion/clap-htsat-unfused','8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a','clap',['*.json','*.txt','*.bin','*.model','LICENSE*'])}
_lock=threading.RLock();_thread=None
_status={'active':False,'phase':'idle','progress':0,'downloaded':0,'total':0,'eta_seconds':None,'error':None}

def evaluate_device(ram_gb,vram_gb,cuda=True,windows=True):
    # Product support floor, not an upstream universal minimum.
    ace=windows and cuda and ram_gb>=15.5 and vram_gb>=3.8
    sa3=ace and ram_gb>=23.5 and vram_gb>=5.8
    return {'ace':bool(ace),'sa3':bool(sa3),'requirements':{
      'ace':'Windows 10/11 x64 · NVIDIA CUDA 显卡 ≥4 GB · 系统内存 ≥16 GB',
      'sa3':'本应用保守支持门槛：NVIDIA 显存 ≥6 GB · 系统内存 ≥24 GB；推理时约需 16 GB 可用内存',
      'disk':'模型与运行环境另计，下载前按实际清单检查空间；另保留 20 GB 系统余量。'}}

def scan_device(consent):
    if consent is not True:raise ValueError('请先明确同意读取 CPU、内存、显卡和可用空间；结果只存本机')
    import psutil,platform
    ram=psutil.virtual_memory();gpu=[]
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if p.returncode==0:
            for row in p.stdout.strip().splitlines():
                name,mem,driver=row.rsplit(',',2);gpu.append({'name':name.strip(),'vram_gb':float(mem)/1024,'driver':driver.strip()})
    except (OSError,subprocess.TimeoutExpired):pass
    result={'platform':platform.system(),'cpu':platform.processor(),'ram_gb':ram.total/1024**3,'available_ram_gb':ram.available/1024**3,'gpus':gpu,'disk_free_gb':shutil.disk_usage(DATA).free/1e9}
    # Current workers use CUDA device 0; never qualify from a different adapter.
    result.update(evaluate_device(result['ram_gb'],gpu[0]['vram_gb'] if gpu else 0,bool(gpu),platform.system()=='Windows'))
    config=read_config();setup=config['setup'];setup.update(scan_consent=True,hardware=result);update_config(setup=setup)
    return result

def required_paths(variant):
    if variant=='stable-audio-3-medium':return [model_root('stable-audio-3-medium')/p for p in ('model.safetensors','model_config.json','t5gemma-b-b-ul2/model.safetensors','t5gemma-b-b-ul2/tokenizer.json')]
    return [model_root('ace-step')/'checkpoints'/p for p in (variant+'/model.safetensors','Qwen3-Embedding-0.6B/model.safetensors','vae/diffusion_pytorch_model.safetensors')]

def model_status():
    from .models import MODELS
    cfg=read_config();hw=cfg.get('setup',{}).get('hardware');legacy=cfg.get('setup',{}).get('legacy_adopted',False)
    return [{**v,'id':k,'installed':all(p.is_file() and p.stat().st_size>0 for p in required_paths(k)),
             'eligible':bool(legacy or (hw and hw['sa3' if k.startswith('stable') else 'ace']))} for k,v in MODELS.items()]

def snapshot():
    with _lock:return dict(_status)

def _set(**values):
    with _lock:_status.update(values)

def _manifest(variant,token):
    from huggingface_hub import HfApi
    repo,revision,subdir,patterns=CATALOG[variant];items=[]
    for item in HfApi(token=token).list_repo_tree(repo,revision=revision,recursive=True):
        if not hasattr(item,'size') or not any(fnmatch.fnmatch(item.path,p) for p in patterns) or item.path.startswith('.'):continue
        if item.path.endswith(('.h5','.msgpack','.onnx')):continue
        # ACE deliberately synchronizes these modules from its pinned source
        # checkout at load time; the HF copy is not the runtime authority.
        if variant.startswith('acestep') and item.path.endswith('.py'):continue
        rel=Path(subdir)/item.path
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('模型清单含非法路径')
        lfs=getattr(item,'lfs',None);sha=(getattr(lfs,'sha256',None) or (lfs.get('sha256') if isinstance(lfs,dict) else None)) if lfs else None
        items.append({'repo':repo,'revision':revision,'remote':item.path,'relative':str(rel),'size':item.size,'sha256':sha})
    if not items:raise ValueError('模型清单为空')
    return items

def _verified(path,item):
    if not path.is_file() or path.stat().st_size!=item['size']:return False
    if not item['sha256']:return True
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']

def _download(items,directory,token):
    import requests
    from huggingface_hub import hf_hub_url
    total=sum(i['size'] for i in items);done=0;started=time.monotonic()
    _set(total=total,phase='verifying',file='正在检查已存在的文件')
    todo=[]
    for item in items:
        target=directory/item['relative']
        if _verified(target,item):done+=item['size']
        else:todo.append(item)
    remaining=sum(i['size'] for i in todo)
    if shutil.disk_usage(directory).free<remaining+20_000_000_000:raise ValueError('模型目录空间不足：下载之外还需保留 20 GB')
    network=0
    for item in todo:
        target=directory/item['relative'];target.parent.mkdir(parents=True,exist_ok=True);part=target.with_name(target.name+'.part')
        offset=part.stat().st_size if part.exists() else 0
        if offset>item['size']:part.unlink();offset=0
        _set(phase='downloading',file=item['relative'])
        if offset<item['size']:
            headers={'Authorization':f'Bearer {token}'} if token else {}
            if offset:headers['Range']=f'bytes={offset}-'
            # requests strips authorization on cross-host redirects.
            with requests.get(hf_hub_url(item['repo'],item['remote'],revision=item['revision']),headers=headers,stream=True,timeout=(20,90)) as response:
                response.raise_for_status()
                if offset and response.status_code!=206:offset=0
                if offset and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('下载服务器未正确续传')
                with part.open('ab' if offset else 'wb') as f:
                    for block in response.iter_content(1024*1024):
                        if not block:continue
                        f.write(block);offset+=len(block);network+=len(block)
                        elapsed=max(.01,time.monotonic()-started);rate=network/elapsed
                        _set(downloaded=done+offset,progress=100*(done+offset)/max(1,total),eta_seconds=int((total-done-offset)/rate) if rate else None)
                    f.flush();os.fsync(f.fileno())
        _set(phase='verifying')
        if not _verified(part,item):
            part.unlink(missing_ok=True);raise ValueError('模型文件校验失败，请重试')
        part.replace(target);done+=item['size']
    _set(downloaded=total,progress=100,eta_seconds=0)

@exclusive
def start_download(variants,directory,token=None,local_only=False):
    global _thread
    from .database import rows
    if not variants or any(v not in CATALOG or v=='clap' for v in variants):raise ValueError('请选择受支持的音乐模型')
    cfg=read_config();hw=cfg.get('setup',{}).get('hardware')
    if not hw or not hw['ace']:raise ValueError('请先完成并通过设备检查')
    if 'stable-audio-3-medium' in variants and not hw['sa3']:raise ValueError('当前设备未达到 SA3 支持门槛')
    if rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"):raise ValueError('请等待生成队列完成后调整模型')
    target=Path(directory).expanduser()
    if not target.is_absolute():raise ValueError('模型位置必须为绝对路径')
    target=target.resolve();target.mkdir(parents=True,exist_ok=True)
    with _lock:
        if _status['active']:raise ValueError('模型下载正在进行')
        _status.update(active=True,phase='manifest',error=None,progress=0,downloaded=0,total=0,file='',eta_seconds=None)
    def work():
        try:
            from huggingface_hub import get_token
            credential=token.strip() if token and token.strip() else get_token()
            chosen=list(dict.fromkeys(['acestep-v15-turbo',*variants,'clap']))
            items=[item for v in chosen for item in _manifest(v,credential)]
            if local_only:
                total=sum(i['size'] for i in items);done=0
                _set(total=total)
                for item in items:
                    _set(phase='verifying',file=item['relative'])
                    if not _verified(target/item['relative'],item):raise ValueError('所选目录缺少或损坏模型文件；可切换为下载补全')
                    done+=item['size'];_set(downloaded=done,progress=100*done/max(1,total))
            else:_download(items,target,credential)
            cfg=read_config();paths=cfg['paths'];paths['models']=str(target);setup=cfg['setup'];setup['models']=chosen;setup['models_verified']=True
            update_config(paths=paths,setup=setup)
            _set(active=False,phase='done',progress=100,eta_seconds=0,error=None)
        except Exception as exc:
            # Never surface request headers, URLs with signed queries or token values.
            name=type(exc).__name__;message=str(exc) if isinstance(exc,ValueError) else '网络、模型授权或文件读写失败；请检查 HF 条款授权、只读 Token 和网络后重试。已下载分片会保留。'
            _set(active=False,phase='failed',error=f'{name}: {message}',eta_seconds=None)
    _thread=threading.Thread(target=work,daemon=True);_thread.start();return snapshot()

def setup_status():
    from .database import rows
    from .preferences import lock,commit_configuration,configuration_revision
    from .migration import manager
    with lock:
        cfg=read_config();s=cfg.get('setup',{});job=None
        if s.get('first_job'):
            found=rows('SELECT id,status,error_code,error FROM jobs WHERE id=?',(s['first_job'],));job=found[0] if found else None
            if not s.get('complete') and not manager.active and job and job['status']=='done' and rows("SELECT id FROM tracks WHERE id=? AND status='ready'",(job['id'],)):
                s['complete']=True
                commit_configuration({'auto_generate':True},None,{},configuration_revision(cfg),setup=s)
    return {'setup':s,'download':snapshot(),'models':model_status(),'config_path':str(DATA/'config.json'),'first_job':job}

@exclusive
def begin_first(library_path,weights,enabled,pins=None):
    from .database import rows
    from .queue import enqueue
    from .preferences import replace_styles
    cfg=read_config();s=cfg['setup']
    if s.get('complete'):raise ValueError('首次设置已完成；请使用高级设置')
    if not s.get('models_verified') or not s.get('hardware',{}).get('ace'):raise ValueError('请先完成设备和模型配置')
    if rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"):raise ValueError('首曲仍在处理中')
    installed={m['id'] for m in model_status() if m['installed']}
    sa3='stable-audio-3-medium' in s.get('models',[]) and 'stable-audio-3-medium' in installed
    if not enabled or any(x not in STYLE_MAP for x in enabled) or (not sa3 and 'guzheng' in enabled):raise ValueError('请选择可用曲风；空谷听泉需要 SA3')
    if any(x not in enabled for x in (pins or [])):raise ValueError('只能固定已选曲风')
    if set(weights)!=set(STYLE_MAP) or any(type(v)!=int or v<0 or v>100 for v in weights.values()) or sum(weights.values())!=100:raise ValueError('曲风比例应为总计 100 的整数百分比')
    if not any(weights[x]>0 for x in enabled):raise ValueError('已选曲风至少一项占比大于 0')
    dest=Path(library_path).expanduser()
    if not dest.is_absolute():raise ValueError('请选择绝对路径')
    import stat
    for part in [dest,*dest.parents]:
        if part.exists() and (part.is_symlink() or getattr(part.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('首次曲库不支持符号链接或目录联接')
    dest=dest.resolve()
    if dest==DATA or any(dest.is_relative_to(DATA/name) for name in ('models','staging','.log','Ambience','Images','CustomAmbience')):
        raise ValueError('请选择独立的空目录，不要使用其他应用数据目录')
    owned=s.get('first_library',{})
    owned_styles=set(owned.get('styles',[])) if owned.get('path')==str(dest) else set()
    # Recognize an attempt made by an older application version too.
    if not owned_styles and s.get('first_job') and cfg['settings']['library_path']==str(dest):
        previous=rows("SELECT style FROM jobs WHERE id=? AND status IN ('failed','cancelled')",(s['first_job'],))
        owned_styles={r['style'] for r in previous}
    dest.mkdir(parents=True,exist_ok=True)
    for child in dest.iterdir():
        if child.name not in owned_styles or not child.is_dir() or child.is_symlink() or getattr(child.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT or any(child.iterdir()):
            raise ValueError('首次曲库请选择空目录；只允许本应用失败任务留下的空曲风目录，不会覆盖已有文件')
    if shutil.disk_usage(dest).free<21_000_000_000:raise ValueError('曲库磁盘至少需要 21 GB 空闲空间')
    gpus=s['hardware'].get('gpus',[])
    if not gpus or not isinstance(gpus[0],dict) or type(gpus[0].get('vram_gb')) not in (int,float) or not 0<gpus[0]['vram_gb']<1000:
        raise ValueError('设备检查不完整，请重新读取显卡信息')
    styles=json.loads(json.dumps(list(STYLE_MAP.values())))
    for style in styles:
        if style['model_variant'] not in s['models'] and style['id']!='guzheng':style['model_variant']='acestep-v15-turbo'
    replace_styles(styles)
    save_settings({'library_path':str(dest),'style_weights':weights,'style_pins':list(dict.fromkeys(pins or [])),'enabled_styles':enabled,'auto_generate':False,'vram_gb':min(6.5,s['hardware']['gpus'][0]['vram_gb']*.82)})
    chosen=max(enabled,key=lambda x:weights[x])
    s['first_library']={'path':str(dest),'styles':sorted(owned_styles|{chosen})};update_config(setup=s)
    job_id=enqueue(chosen,180)
    s['first_job']=job_id;update_config(setup=s);return setup_status()
