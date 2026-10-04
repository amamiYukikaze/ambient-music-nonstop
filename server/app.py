"""Loopback-only authenticated API. Electron owns the service and ephemeral token."""
import json
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from .config import DATA, PROJECT, STYLES, STYLE_MAP, safe_path
from .database import initialize, settings, connection, rows
from .library import tracks, choose, start_play, ping_play, retire
from .queue import Producer, enqueue, refill_plan
from .models import MODELS
from .migration import manager as migration
from .preferences import read_config,save_settings,replace_styles,update_config,validate_styles,configuration_revision,commit_configuration
from . import provisioning,assets
from .operation_lock import exclusive

TOKEN=os.environ.get('AMBIENT_API_TOKEN') or secrets.token_urlsafe(32)
VERSION=json.loads((PROJECT/'package.json').read_text(encoding='utf8'))['version']
producer=Producer()


@asynccontextmanager
async def lifespan(app):
    initialize(recover=os.environ.get('AMBIENT_NO_WORKER')!='1')
    migration.restore()
    if os.environ.get('AMBIENT_NO_WORKER')!='1':producer.start()
    yield
    if producer.thread.is_alive():producer.close()


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)


@app.middleware('http')
async def authenticate(request:Request,call_next):
    if not secrets.compare_digest(request.headers.get('x-ambient-token',''),TOKEN):
        return JSONResponse({'detail':'Unauthorized'},status_code=401)
    startup_read=request.method=='GET' and request.url.path in ('/health','/setup')
    if migration.active and request.url.path!='/library-move' and not startup_read:
        return JSONResponse({'detail':'曲库迁移中，播放与修改暂时不可用'},status_code=423)
    if request.url.path.split('/')[1] in ('next','plays','audio','jobs') and not read_config().get('setup',{}).get('complete',False):
        return JSONResponse({'detail':'请先完成首次设置与首曲生成'},status_code=423)
    return await call_next(request)


class JobRequest(BaseModel):
    style:str='lofi'
    duration:int|None=Field(default=None,ge=30,le=180)
    count:int=Field(default=1,ge=1,le=4)


class PlayRequest(BaseModel):
    track_id:str=Field(pattern=r'^[a-f0-9]{32}$')


class PingRequest(BaseModel):
    playing:bool=True
    finish:bool=False
    reason:Literal['ended','skip','pause','error','delete','close']='ended'


class SettingsPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    auto_generate:bool|None=None
    enabled_styles:list[str]|None=None
    capacity_gb:int|None=Field(default=None,ge=1,le=150)
    duration:int|None=Field(default=None,ge=30,le=180)
    style_weights:dict[str,int]|None=None
    style_pins:list[str]|None=None
    crossfade:int|None=Field(default=None,ge=0,le=15)
    plays_before_retire:int|None=Field(default=None,ge=1,le=100)
    minimum_free_gb:int|None=Field(default=None,ge=5,le=200)
    generation_interval:int|None=Field(default=None,ge=5,le=3600)
    vram_gb:float|None=Field(default=None,ge=2,le=80)


class MigrationRequest(BaseModel):
    destination:str=Field(min_length=3,max_length=1000)


@app.get('/library-move')
def migration_status():return migration.snapshot()


@app.post('/library-move')
def move_library(request:MigrationRequest):
    try:return migration.start(request.destination)
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))


@app.get('/health')
def health():return {'ok':True,'version':VERSION,'data_root':str(DATA),'process_id':os.getpid(),'config_recovery':read_config().get('recovery'),'library_migration':migration.snapshot()}


@app.get('/state')
def state():
    pool=rows("SELECT style,COUNT(*) AS count,SUM(bytes) AS bytes,SUM(duration) AS seconds FROM tracks WHERE status='ready' GROUP BY style")
    archive=rows("SELECT COALESCE(SUM(bytes),0) AS bytes,SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) AS review_count FROM tracks WHERE status IN ('ready','retiring','review')")[0]
    jobs=rows("SELECT *,json_extract(params,'$.model_variant') model_variant FROM jobs ORDER BY created DESC LIMIT 20")
    for job in jobs:job['model_name']=MODELS.get(job['model_variant'],{}).get('name',job['model_variant'])
    return dict(styles=STYLES,settings=settings(),pool=pool,tracks=tracks(),archive=archive,refill=refill_plan(),
        jobs=jobs,
        events=rows('SELECT * FROM events ORDER BY id DESC LIMIT 30'),disk_free=shutil.disk_usage(DATA).free,
        ambience=assets.ambience_items(),images=read_config().get('images',[]),models=provisioning.model_status())


@app.get('/next')
def next_track(style:str|None=None,exclude:str|None=None):
    if style and style not in STYLE_MAP:raise HTTPException(400,'Unknown style')
    return {'track':choose(style,exclude)}


@app.post('/jobs')
def jobs(request:JobRequest):
    spec=STYLE_MAP.get(request.style)
    if spec and not any(m['id']==spec['model_variant'] and m['eligible'] and m['installed'] for m in provisioning.model_status()):raise HTTPException(400,'此曲风需要先安装并启用对应模型')
    try:return {'ids':[enqueue(request.style,request.duration) for _ in range(request.count)]}
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.patch('/settings')
def update_settings(request:SettingsPatch):
    values=request.model_dump(exclude_none=True)
    if 'style_pins' in values and any(s not in STYLE_MAP for s in values['style_pins']):raise HTTPException(400,'Unknown pinned style')
    if 'style_weights' in values:
        weights=values['style_weights']
        if set(weights)!=set(STYLE_MAP) or any(v<0 or v>1000 for v in weights.values()) or sum(weights.values())<=0:
            raise HTTPException(400,'All styles need weights from 0 to 1000, with a positive total')
    if 'enabled_styles' in values:
        if any(s not in STYLE_MAP for s in values['enabled_styles']):raise HTTPException(400,'Unknown style')
        values['enabled_styles']=list(dict.fromkeys(values['enabled_styles']))
        available={m['id'] for m in provisioning.model_status() if m['installed'] and m['eligible']}
        added=set(values['enabled_styles'])-set(settings()['enabled_styles'])
        if any(STYLE_MAP[s]['model_variant'] not in available for s in added):raise HTTPException(400,'请先通过设备检查，并安装该曲风使用的模型')
    save_settings(values)
    return settings()


@app.post('/plays')
def play(request:PlayRequest):
    try:return {'session_id':start_play(request.track_id)}
    except ValueError as exc:raise HTTPException(404,str(exc))


@app.post('/plays/{session_id}')
def ping(session_id:str,request:PingRequest):return ping_play(session_id,**request.model_dump())


@app.delete('/tracks/{track_id}')
def delete(track_id:str):return {'retired':retire(track_id,'manual_delete')}


@app.get('/audio/{track_id}')
def audio(track_id:str):
    data=rows("SELECT path FROM tracks WHERE id=? AND status='ready'",(track_id,))
    if not data:raise HTTPException(404,'Unavailable track')
    p=safe_path(data[0]['path'])
    if not p.exists():raise HTTPException(404,'Missing file')
    return FileResponse(p,media_type='audio/flac' if p.suffix=='.flac' else 'audio/ogg')


@app.get('/ambience/{id}')
def ambience(id:str):
    ambience_info(id)
    return FileResponse(assets.ambience_path(id),media_type='audio/ogg')

@app.get('/ambience/{id}/info')
def ambience_info(id:str):
    try:return assets.ambience_info(id)
    except assets.AmbienceLimitError as exc:raise HTTPException(413,str(exc))
    except (ValueError,OSError) as exc:raise HTTPException(404,str(exc))
    except RuntimeError:raise HTTPException(400,'无法读取环境声音频，请重新导入')

class DeviceRequest(BaseModel):
    consent:bool

class DownloadRequest(BaseModel):
    models:list[str]
    directory:str
    token:str|None=Field(default=None,repr=False,max_length=500)
    local_only:bool=False

class FirstRequest(BaseModel):
    library_path:str
    weights:dict[str,int]
    enabled:list[str]
    pins:list[str]=[]

class ImportRequest(BaseModel):
    kind:Literal['images','ambience']
    source:str
    name:str
    icon:str='♪'
    environment:str='city'
    period:str='any'
    styles:list[str]=[]
    focus:list[float]=[.5,.5]

@app.get('/setup')
def setup_state():return provisioning.setup_status()

@app.post('/setup/scan')
def scan(request:DeviceRequest):
    try:return provisioning.scan_device(request.consent)
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/setup/models')
def download(request:DownloadRequest):
    try:return provisioning.start_download(request.models,request.directory,request.token,request.local_only)
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/setup/first')
def first(request:FirstRequest):
    try:return provisioning.begin_first(request.library_path,request.weights,request.enabled,request.pins)
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/configuration')
def configuration():
    cfg=read_config()
    return {'config':cfg,'revision':configuration_revision(cfg),'models':provisioning.model_status(),'config_path':str(DATA/'config.json')}

class ConfigurationSave(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:str=Field(min_length=64,max_length=64)
    settings:SettingsPatch=Field(default_factory=SettingsPatch)
    styles:list[dict]|None=None
    paths:dict[str,str]=Field(default_factory=dict)

@app.put('/configuration/save')
@exclusive
def save_configuration(request:ConfigurationSave):
    from pathlib import Path
    from .database import now
    values=request.settings.model_dump(exclude_none=True);styles=None;paths={}
    try:
        if request.styles is not None and request.styles!=STYLES:
            styles=validate_styles(request.styles)
            if rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"):raise HTTPException(409,'生成队列尚未完成；配方草稿已保留，请稍后保存')
        current={s['id']:s for s in (styles or STYLES)}
        available={m['id'] for m in provisioning.model_status() if m['eligible'] and m['installed']}
        for s in styles or []:
            old=STYLE_MAP.get(s['id'])
            if (not old or old['model_variant']!=s['model_variant']) and s['model_variant'] not in available:raise ValueError('请先安装并启用所选模型')
            if s['id']=='guzheng' and s['model_variant']!='stable-audio-3-medium':raise ValueError('空谷听泉必须使用 SA3')
            if s!=old:s['prompt_revision']='user-'+now()
        if 'style_weights' in values:
            w=values['style_weights']
            if set(w)!=set(current) or any(v<0 or v>100 for v in w.values()) or sum(w.values())!=100:raise ValueError('所有曲风比例需合计为 100%')
        elif styles is not None:values['style_weights']={s:settings()['style_weights'].get(s,0) for s in current}
        if any(s not in current for s in values.get('style_pins',[])):raise ValueError('存在未知固定曲风')
        if 'enabled_styles' in values:
            if any(s not in current for s in values['enabled_styles']):raise ValueError('存在未知曲风')
            if any(current[s]['model_variant'] not in available for s in set(values['enabled_styles'])-set(settings()['enabled_styles'])):raise ValueError('请先安装并启用对应模型')
        if set(request.paths)-{'images','ambience'}:raise ValueError('音乐迁移和模型验证请使用专用操作')
        for key,value in request.paths.items():
            p=Path(value).expanduser()
            if not p.is_absolute():raise ValueError('素材保存位置需要绝对路径')
            paths[key]=str(p.resolve())
        if configuration_revision()!=request.revision:raise HTTPException(409,'设置已在其他操作中更新；请重新载入后再编辑')
        for value in paths.values():Path(value).mkdir(parents=True,exist_ok=True)
        commit_configuration(values,styles,paths,request.revision)
        return configuration()
    except (ValueError,TypeError,KeyError,OSError) as exc:raise HTTPException(400,str(exc))

@app.put('/configuration/styles')
@exclusive
def edit_styles(styles:list[dict]):
    if rows("SELECT id FROM jobs WHERE status IN ('queued','running','processing')"):raise HTTPException(409,'请等待队列完成后修改配方')
    eligible={m['id'] for m in provisioning.model_status() if m['installed'] and m['eligible']}
    for s in styles:
        old=STYLE_MAP.get(s.get('id'))
        if (not old or s.get('model_variant')!=old.get('model_variant')) and s.get('model_variant') not in eligible:raise HTTPException(400,'请先验证设备并下载所选模型')
        if s.get('id')=='guzheng' and s.get('model_variant')!='stable-audio-3-medium':raise HTTPException(400,'空谷听泉必须使用 SA3')
    try:return replace_styles(styles)
    except (ValueError,TypeError) as e:raise HTTPException(400,str(e))

@app.patch('/configuration/paths')
def asset_paths(paths:dict[str,str]):
    from pathlib import Path
    if set(paths)-{'images','ambience'}:raise HTTPException(400,'曲库请使用迁移功能；模型位置请通过验证')
    cfg=read_config()
    for key,value in paths.items():
        p=Path(value).expanduser()
        if not p.is_absolute():raise HTTPException(400,'需要绝对路径')
        p.mkdir(parents=True,exist_ok=True);cfg['paths'][key]=str(p.resolve())
    update_config(paths=cfg['paths']);return cfg['paths']

@app.post('/assets/import')
def asset_import(request:ImportRequest):
    try:return assets.import_asset(**request.model_dump())
    except (ValueError,OSError) as e:raise HTTPException(400,str(e))

@app.get('/images/{id}')
def image(id:str):
    try:return FileResponse(assets.media_path('images',id),media_type='image/webp')
    except ValueError as e:raise HTTPException(404,str(e))


if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('AMBIENT_PORT','49321')),log_level='warning')
