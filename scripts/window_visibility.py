"""Windows visible-client-region probe. Stdlib only; no screen capture or titles.

Subtract opaque windows above the player from its on-screen client region.
Translucent/per-pixel layered windows are conservatively treated as see-through.
"""
import ctypes as c
from ctypes import wintypes as w
import json
import sys
import time

user=c.WinDLL('user32',use_last_error=True)
gdi=c.WinDLL('gdi32',use_last_error=True)
dwm=c.WinDLL('dwmapi',use_last_error=True)
def bind(lib,name,args,result):
    fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
RECT=w.RECT; PTR=c.c_void_p
is_window=bind(user,'IsWindow',[PTR],w.BOOL)
is_visible=bind(user,'IsWindowVisible',[PTR],w.BOOL)
is_iconic=bind(user,'IsIconic',[PTR],w.BOOL)
get_rect=bind(user,'GetWindowRect',[PTR,c.POINTER(RECT)],w.BOOL)
get_client=bind(user,'GetClientRect',[PTR,c.POINTER(RECT)],w.BOOL)
to_screen=bind(user,'ClientToScreen',[PTR,c.POINTER(w.POINT)],w.BOOL)
top=bind(user,'GetTopWindow',[PTR],PTR)
next_window=bind(user,'GetWindow',[PTR,w.UINT],PTR)
style=bind(user,'GetWindowLongPtrW',[PTR,c.c_int],c.c_ssize_t)
attribute=bind(dwm,'DwmGetWindowAttribute',[PTR,w.DWORD,PTR,w.DWORD],c.c_long)
new_region=bind(gdi,'CreateRectRgn',[c.c_int]*4,PTR)
combine=bind(gdi,'CombineRgn',[PTR,PTR,PTR,c.c_int],c.c_int)
region_box=bind(gdi,'GetRgnBox',[PTR,c.POINTER(RECT)],c.c_int)
delete=bind(gdi,'DeleteObject',[PTR],w.BOOL)
window_region=bind(user,'GetWindowRgn',[PTR,PTR],c.c_int)
offset_region=bind(gdi,'OffsetRgn',[PTR,c.c_int,c.c_int],c.c_int)
layer_attributes=bind(user,'GetLayeredWindowAttributes',[PTR,c.POINTER(w.DWORD),c.POINTER(w.BYTE),c.POINTER(w.DWORD)],w.BOOL)
MONITOR_CB=c.WINFUNCTYPE(w.BOOL,PTR,PTR,c.POINTER(RECT),w.LPARAM)
enum_monitors=bind(user,'EnumDisplayMonitors',[PTR,PTR,MONITOR_CB,w.LPARAM],w.BOOL)
try:user.SetProcessDpiAwarenessContext(c.c_void_p(-4))
except (AttributeError,OSError):pass

def cloaked(hwnd):
    value=w.DWORD();return attribute(hwnd,14,c.byref(value),c.sizeof(value))==0 and value.value!=0

def probe(hwnd):
    if not is_visible(hwnd) or is_iconic(hwnd) or cloaked(hwnd):return False
    client=RECT(); origin=w.POINT()
    if not get_client(hwnd,c.byref(client)) or not to_screen(hwnd,c.byref(origin)):return True
    region=new_region(origin.x,origin.y,origin.x+client.right,origin.y+client.bottom)
    monitors=new_region(0,0,0,0)
    try:
        @MONITOR_CB
        def monitor(_,dc,r,data):
            rect=r.contents;part=new_region(rect.left,rect.top,rect.right,rect.bottom)
            try:combine(monitors,monitors,part,2)
            finally:delete(part)
            return True
        if not enum_monitors(None,None,monitor,0):return True
        if combine(region,region,monitors,1)==1:return False
        above=top(None); visited=set()
        while above and above!=hwnd and above not in visited:
            visited.add(above)
            if is_visible(above) and not is_iconic(above) and not cloaked(above):
                ex=style(above,-20);opaque=not (ex&0x20)
                if ex&0x80000:
                    key=w.DWORD();alpha=w.BYTE();flags=w.DWORD()
                    opaque=opaque and bool(layer_attributes(above,c.byref(key),c.byref(alpha),c.byref(flags))) and bool(flags.value&2) and alpha.value==255 and not(flags.value&1)
                if opaque:
                    rect=RECT()
                    if attribute(above,9,c.byref(rect),c.sizeof(rect))!=0:get_rect(above,c.byref(rect))
                    part=new_region(rect.left,rect.top,rect.right,rect.bottom)
                    shape=new_region(0,0,0,0)
                    try:
                        # Honor explicit nonrectangular window regions when present.
                        if window_region(above,shape)>0:
                            raw=RECT();get_rect(above,c.byref(raw));offset_region(shape,raw.left,raw.top);combine(part,part,shape,1)
                        if combine(region,region,part,4)==1:return False
                    finally:delete(shape);delete(part)
            above=next_window(above,2)
        box=RECT();return region_box(region,c.byref(box))!=1
    finally:delete(monitors);delete(region)

if __name__=='__main__':
    hwnd=int(sys.argv[1]);last=None
    while is_window(hwnd):
        try:value=probe(hwnd)
        except Exception:value=True  # Probe failure must not leave a visible room frozen.
        if value!=last:print(json.dumps({'visible':value}),flush=True);last=value
        time.sleep(.5)
