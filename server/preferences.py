"""Portable, atomic user configuration; SQLite remains the music/history store."""
import copy
import json
import os
import threading
import hashlib
from pathlib import Path
from .config import CONFIG_FILE,DATA,STYLES,STYLE_MAP,DEFAULTS
from .models import MODELS
from .config_schema import CONFIG_VERSION, normalize, absolute_path

lock=threading.RLock()
LAST_GOOD=CONFIG_FILE.with_name('config.last-good.json')
_cached_config=None
_disk_bytes=None
_bundled_styles=copy.deepcopy(STYLES)

def _validate_loaded_styles(styles):
    return validate_styles(styles,required_ids={s['id'] for s in _bundled_styles})

def read_config():
    with lock:
        if _cached_config is None:
            raise RuntimeError('Configuration has not been initialized')
        return copy.deepcopy(_cached_config)


def load_worker_config():
    """An isolated QC worker needs paths, without replaying startup DB recovery."""
    global _cached_config
    with lock:
        for path in (CONFIG_FILE,LAST_GOOD):
            try:
                document=json.loads(path.read_text(encoding='utf-8-sig'))
                config,issues=normalize(document,DEFAULTS,_bundled_styles,DATA,_validate_loaded_styles)
            except (OSError,ValueError,UnicodeError):
                continue
            if not issues:
                _cached_config=copy.deepcopy(config)
                STYLES[:]=config['styles'];STYLE_MAP.clear();STYLE_MAP.update({s['id']:s for s in STYLES})
                return read_config()
        raise RuntimeError('No valid configuration snapshot for QC; restart the application to recover settings')

def _atomic_json(path,config):
    tmp=path.with_suffix('.json.part')
    with tmp.open('w',encoding='utf8') as f:
        json.dump(config,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def _preserve(raw):
    path=CONFIG_FILE.with_name('config.rejected-'+hashlib.sha256(raw).hexdigest()[:16]+'.json')
    if not path.exists():
        with path.open('xb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
    elif path.read_bytes()!=raw:
        raise OSError('Configuration recovery backup collision')
    return str(path)

def write_config(config):
    global _cached_config,_disk_bytes
    with lock:
        validated,issues=normalize(config,DEFAULTS,_bundled_styles,DATA,_validate_loaded_styles)
        if issues:raise ValueError('Invalid configuration: '+', '.join(issues))
        CONFIG_FILE.parent.mkdir(parents=True,exist_ok=True)
        if CONFIG_FILE.exists() and _disk_bytes is not None:
            raw=CONFIG_FILE.read_bytes()
            if raw!=_disk_bytes:_preserve(raw)
        # Commit the previous valid state first, so a failed replacement retains it.
        _atomic_json(LAST_GOOD,_cached_config or validated)
        _atomic_json(CONFIG_FILE,validated)
        _cached_config=copy.deepcopy(validated);_disk_bytes=CONFIG_FILE.read_bytes()

def update_config(**values):
    with lock:
        config=read_config();config.update(values);write_config(config);return config

def initialize_config(registered=None):
    global _cached_config,_disk_bytes
    from .database import connection
    with lock,connection() as db:
        legacy=bool(db.execute('SELECT 1 FROM tracks LIMIT 1').fetchone())
        def load(path):
            raw=path.read_bytes() if path.exists() else None
            try:document=json.loads(raw.decode('utf-8-sig')) if raw is not None else None
            except (ValueError,UnicodeError):document=None
            config,issues=normalize(document,DEFAULTS,_bundled_styles,DATA,_validate_loaded_styles,registered,legacy)
            return raw,document,config,issues
        raw,document,config,issues=load(CONFIG_FILE)
        _disk_bytes=raw
        recovery=raw is not None and bool(issues)
        if issues:
            backup_raw,backup_document,backup,backup_issues=load(LAST_GOOD)
            source='defaults' if document is None else 'validated-fields'
            if backup_raw is not None and not backup_issues:
                config=backup;source='last-known-good'
            if raw is None and legacy:
                config['setup'].update(complete=True,legacy_adopted=True)
            # Path registration survives even an unknown future config schema.
            paths=[(registered or {}).get('library_path'),config['settings'].get('library_path')]
            if isinstance(document,dict) and isinstance(document.get('settings'),dict):
                incoming=document['settings'].get('library_path')
                if absolute_path(incoming):
                    paths.append(incoming)
                    if source!='last-known-good' and not absolute_path((registered or {}).get('library_path')):
                        config['settings']['library_path']=incoming
            config['settings']['auto_generate']=False
            if recovery:
                original=_preserve(raw)
                config['recovery']={'status':'recovered','source':source,'original':original,
                    'issues':issues,'library_paths':list(dict.fromkeys(p for p in paths if absolute_path(p))),
                    'message':'配置已安全恢复，自动补库已暂停。请检查高级设置后再开启；原配置与数据库已保留。'}
        # SQLite is authoritative after a migration commits, even for an empty library.
        if absolute_path((registered or {}).get('library_path')):
            config['settings']['library_path']=registered['library_path']
        _cached_config=copy.deepcopy(config)
        STYLES[:]=config['styles'];STYLE_MAP.clear();STYLE_MAP.update({s['id']:s for s in STYLES})
        write_config(config)
        for key,value in config['settings'].items():
            if key in DEFAULTS:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))

def save_settings(values):
    from .database import connection
    with lock:
        config=read_config();config.setdefault('settings',{}).update(values)
        write_config(config)
        with connection() as db:
            for key,value in values.items():db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))

def sync_library_path(path):
    # Called only after the existing transactional library migration commits.
    with lock:
        config=read_config();config.setdefault('settings',{})['library_path']=str(path);write_config(config)

def validate_styles(styles,required_ids=None):
    if not isinstance(styles,list) or not 1<=len(styles)<=32:raise ValueError('曲风数量应为 1–32')
    import re
    seen=set()
    for s in styles:
        if not isinstance(s,dict):raise ValueError('每个曲风都需要一个配置对象')
        ident=s.get('id','')
        if not isinstance(ident,str) or not re.fullmatch('[a-z][a-z0-9_]{0,39}',ident) or ident in seen:raise ValueError('风格 ID 必须唯一，只含小写字母、数字和下划线')
        seen.add(ident)
        for key in ('name','subtitle'):
            if not isinstance(s.get(key),str) or not 1<=len(s[key])<=120:raise ValueError(f'{key} 需要 1–120 个字符')
        if s.get('model_variant') not in MODELS:raise ValueError('不支持此模型')
        bpm=s.get('bpm')
        if bpm is not None and (not isinstance(bpm,list) or len(bpm)!=2 or any(type(x)!=int for x in bpm) or not 30<=bpm[0]<=bpm[1]<=240):raise ValueError('BPM 范围应在 30–240，散板可用 null')
        prompts=s.get('prompts')
        if not isinstance(prompts,list) or not 1<=len(prompts)<=16 or any(not isinstance(p,str) or not p.strip() or len(p)>2500 for p in prompts):raise ValueError('需要 1–16 条提示词，每条不超过 2500 字符；模型仍有 256 token 上限')
        for key in ('instruments','moods'):
            if not isinstance(s.get(key),list) or any(not isinstance(x,str) or len(x)>120 for x in s[key]):raise ValueError(f'{key} 应为短文本数组')
        if s.get('tonal_policy','major-v6') not in ('major-v6','gong-pentatonic-prompt-only','prompt-only'):raise ValueError('未知调性策略')
        from .tonality import MAJOR_KEYS
        if not s.get('keys',list(MAJOR_KEYS)) or any(k not in MAJOR_KEYS for k in s.get('keys',MAJOR_KEYS)):raise ValueError('调性必须来自支持的大调列表')
        if s.get('timesignature','4') not in ('2','3','4','6','free'):raise ValueError('拍号应为 2、3、4、6 或 free')
        if s.get('lm_enabled',False):raise ValueError('此发布配置使用直接文本生成，暂不启用额外 LM')
        enc=s.get('encoding',{})
        if not isinstance(enc,dict):raise ValueError('编码配置应为对象')
        if enc.get('codec','opus') not in ('opus','flac') or enc.get('bitrate_kbps',192) not in (96,128,160,192,256,320):raise ValueError('编码应为 Opus 96–320 kbps 或 FLAC')
        if type(s.get('weight')) not in (int,float) or not 0<=s['weight']<=100:raise ValueError('默认配比应为 0–100')
        if type(s.get('shift',1)) not in (int,float) or not .1<=s.get('shift',1)<=5:raise ValueError('shift 应为 0.1–5')
    # Keep known identities: old music and its logs must remain addressable.
    if not set(STYLE_MAP if required_ids is None else required_ids)<=seen:raise ValueError('请将风格权重设为 0 并禁用补库，不要删除已有风格 ID')
    return copy.deepcopy(styles)

def replace_styles(styles):
    from .database import settings,now
    styles=validate_styles(styles)
    for s in styles:
        if s!=STYLE_MAP.get(s['id']):s['prompt_revision']='user-'+now()
    with lock:
        update_config(styles=styles)
        STYLES[:]=styles;STYLE_MAP.clear();STYLE_MAP.update({s['id']:s for s in styles})
        weights=settings()['style_weights']
        for s in styles:weights.setdefault(s['id'],0)
        save_settings({'style_weights':weights})
    return styles

def configuration_revision(config=None):
    config=config or read_config()
    editable={'settings':config['settings'],'styles':config['styles'],
              'paths':{k:config['paths'][k] for k in ('images','ambience')}}
    return hashlib.sha256(json.dumps(editable,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def commit_configuration(values,styles,paths,expected_revision,setup=None):
    """Commit one validated edit session; keep SQLite and the public JSON aligned."""
    from .database import connection
    with lock:
        original=read_config()
        if configuration_revision(original)!=expected_revision:raise ValueError('设置已在其他操作中更新；请保留草稿并重新载入，避免覆盖新设置')
        updated=copy.deepcopy(original);updated['settings'].update(values);updated['paths'].update(paths)
        if styles is not None:updated['styles']=styles
        if setup is not None:updated['setup']=setup
        try:
            with connection() as db:
                db.execute('BEGIN IMMEDIATE')
                for key,value in values.items():db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
                write_config(updated)
        except Exception:
            write_config(original)
            raise
        if styles is not None:
            STYLES[:]=styles;STYLE_MAP.clear();STYLE_MAP.update({s['id']:s for s in styles})
        return updated
