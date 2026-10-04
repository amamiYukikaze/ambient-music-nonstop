"""Serialize music-file mutations with directory migration within the service."""
from functools import wraps
from threading import RLock

gate=RLock()

def exclusive(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with gate:return fn(*args,**kwargs)
    return wrapped
