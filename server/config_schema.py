"""Versioned config shape and conservative field recovery; no filesystem writes."""
import copy
import math
from pathlib import Path

CONFIG_VERSION = 2
SUPPORTED_VERSIONS = (1, CONFIG_VERSION)


def absolute_path(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value and Path(value).is_absolute()


def normalize(raw, defaults, styles, data, validate_styles, registered=None, legacy=False):
    issues = []
    if not isinstance(raw, dict):
        issues.append('configuration must be an object')
        raw = {}
    version = raw.get('version')
    supported = type(version) is int and version in SUPPORTED_VERSIONS
    if not supported:
        issues.append('missing or unsupported configuration version')
    candidate = copy.deepcopy(raw) if supported else {}
    config = copy.deepcopy(candidate)
    config['version'] = CONFIG_VERSION
    try:
        config['styles'] = validate_styles(candidate.get('styles'))
    except (ValueError, TypeError, KeyError, OverflowError):
        config['styles'] = copy.deepcopy(styles)
        issues.append('invalid or missing styles')
    ids = {s['id'] for s in config['styles']}
    aliases = {'bright_piano': 'daily_piano', 'hybrid': 'orchestral'}
    bounds = {'capacity_gb': (1, 150), 'duration': (30, 180), 'crossfade': (0, 15),
              'plays_before_retire': (1, 100), 'minimum_free_gb': (5, 200),
              'generation_interval': (5, 3600), 'vram_gb': (2, 80),
              'target_lufs': (-40, -5), 'true_peak': (-12, 0)}

    def valid_setting(key, value):
        if key == 'auto_generate':
            return type(value) is bool
        if key == 'library_path':
            return absolute_path(value)
        if key in ('enabled_styles', 'style_pins'):
            return isinstance(value, list) and all(isinstance(s, str) and aliases.get(s, s) in ids for s in value)
        if key == 'style_weights':
            return isinstance(value, dict) and bool(value) and all(
                isinstance(s, str) and aliases.get(s, s) in ids and type(v) in (int, float)
                and math.isfinite(v) and 0 <= v <= 1000 for s, v in value.items()) and sum(value.values()) > 0
        lo, hi = bounds[key]
        return type(value) in ((int,) if type(defaults[key]) is int else (int, float)) and math.isfinite(value) and lo <= value <= hi

    settings = copy.deepcopy(defaults)
    settings['style_weights'] = {s['id']: s.get('weight', 0) for s in config['styles']}
    for key, value in (registered or {}).items():
        if key in defaults and valid_setting(key, value):
            settings[key] = copy.deepcopy(value)
    supplied = candidate.get('settings')
    if not isinstance(supplied, dict):
        supplied = {}
    for key in defaults:
        if key not in supplied or not valid_setting(key, supplied[key]):
            issues.append('invalid or missing settings.' + key)
        else:
            settings[key] = copy.deepcopy(supplied[key])
    for key in ('enabled_styles', 'style_pins'):
        settings[key] = list(dict.fromkeys(aliases.get(s, s) for s in settings[key] if aliases.get(s, s) in ids))
    settings['style_weights'] = {aliases.get(s, s): v for s, v in settings['style_weights'].items() if aliases.get(s, s) in ids}
    for ident in ids:
        settings['style_weights'].setdefault(ident, 0)
    config['settings'] = settings
    paths = candidate.get('paths')
    config['paths'] = {}
    for key, folder in [('models', 'models'), ('images', 'Images'), ('ambience', 'CustomAmbience')]:
        value = paths.get(key) if isinstance(paths, dict) else None
        if not absolute_path(value):
            value = str(data / folder)
            issues.append('invalid or missing paths.' + key)
        config['paths'][key] = value
    setup = candidate.get('setup')
    if not isinstance(setup, dict):
        setup = {}
    config['setup'] = copy.deepcopy(setup)
    for key, default in [('complete', legacy), ('legacy_adopted', legacy), ('scan_consent', False)]:
        if type(setup.get(key)) is not bool:
            config['setup'][key] = default
            issues.append('invalid or missing setup.' + key)
    for key, check in {
        'models_verified': lambda v: type(v) is bool,
        'models': lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
        'first_job': lambda v: isinstance(v, str) and len(v) == 32 and all(c in '0123456789abcdef' for c in v),
        'hardware': lambda v: isinstance(v, dict) and type(v.get('ace')) is bool and type(v.get('sa3')) is bool,
        'first_library': lambda v: isinstance(v, dict) and absolute_path(v.get('path')) and isinstance(v.get('styles'),list) and all(isinstance(s,str) and s in ids for s in v['styles']),
    }.items():
        if key in setup and not check(setup[key]):
            config['setup'].pop(key, None)
            issues.append('invalid setup.' + key)
    for kind in ('images', 'ambience'):
        items = candidate.get(kind)
        config[kind] = []
        if not isinstance(items, list):
            issues.append('invalid or missing ' + kind)
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not absolute_path(item.get('path')) or not isinstance(item.get('name'), str):
                issues.append('invalid ' + kind + ' entry')
            else:
                config[kind].append(copy.deepcopy(item))
    return config, list(dict.fromkeys(issues))
