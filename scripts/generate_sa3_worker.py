"""Production SA3 worker: shared producer lease is owned by the parent process."""
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from worker_watchdog import start as start_watchdog
start_watchdog()
from sa3_audition import ROOT, CODE_REVISION, MODEL_REVISION, render

request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
out=Path(request['output']);out.mkdir(parents=True,exist_ok=True)
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
started=time.monotonic();stage='model_load_error';peak_rss=0
stop=threading.Event();result={}
import psutil
def monitor():
    global peak_rss
    process=psutil.Process()
    while not stop.wait(.25):peak_rss=max(peak_rss,process.memory_info().rss)
threading.Thread(target=monitor,daemon=True).start()
try:
    import torch
    import soundfile as sf
    from stable_audio_3.loading_utils import load_diffusion_cond
    from stable_audio_3.models import transformer
    torch.set_num_threads(6)
    if sys.platform=='win32':
        transformer.flex_attention_available=False
        transformer.flex_attention_compiled=None
    from source_revision import revision
    if revision(ROOT/'vendor/stable-audio-3')!=CODE_REVISION:raise RuntimeError('SA3 source revision changed; adapter must be revalidated')
    model_dir=Path(request['model_root'])
    cfg=json.loads((model_dir/'model_config.json').read_text(encoding='utf-8'))
    for item in cfg['model']['conditioning']['configs']:
        if item['type']=='t5gemma':item['config']['model_path']=str(model_dir.resolve())
    previous=torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float16)
        core=load_diffusion_cond(cfg,str(model_dir/'model.safetensors'),device='cpu',model_half=True)
    finally:torch.set_default_dtype(previous)
    core.conditioner.float();core.conditioner.conditioners['prompt'].model.float()
    count=len(core.conditioner.conditioners['prompt'].tokenizer(request['prompt'])['input_ids'])
    if count>256:raise ValueError(f'conditioning_text_too_long: {count}')
    load_seconds=time.monotonic()-started
    stage='generation_error'
    device='cuda' if torch.cuda.is_available() else 'cpu'
    if device=='cuda':
        torch.cuda.set_per_process_memory_fraction(min(.95,float(request.get('vram_gb',6.5))*1024**3/torch.cuda.get_device_properties(0).total_memory))
    duration=max(120,min(180,float(request['duration'])))
    attempts=[(device,duration)]
    if device=='cuda':
        if duration>120:attempts.append(('cuda',120))
        attempts.append(('cpu',120))
    fallbacks=[]
    item={'id':out.name,'prompt':request['prompt'],'seed':request['seed']}
    for device,duration in attempts:
        metrics={};oom=False
        try:audio=render(core,cfg,item,duration,device,metrics)
        except torch.cuda.OutOfMemoryError:
            if device!='cuda':raise
            fallbacks.append({'device':device,'duration':duration,'error_code':'cuda_oom'})
            print(json.dumps({'event':'cuda_oom','duration':duration,'next':'shorter GPU or CPU fallback'}),flush=True)
            oom=True
        if not oom:break
        gc.collect();torch.cuda.empty_cache()
    else:raise RuntimeError('SA3 inference attempts exhausted')
    if len(audio)!=int(duration*cfg['sample_rate']):
        raise RuntimeError(f'Generated duration mismatch: {len(audio)/cfg["sample_rate"]} != {duration}')
    stage='filesystem_error'
    path=out/'generated.wav';sf.write(str(path),audio,cfg['sample_rate'],subtype='FLOAT')
    result=dict(success=True,path=str(path),model='Stable Audio 3 Medium',model_variant='stable-audio-3-medium',
                model_revision=MODEL_REVISION,source_revision=CODE_REVISION,sample_rate=cfg['sample_rate'],
                duration_requested=duration,original_duration_requested=request['duration'],seed=request['seed'],
                conditioning_tokens=count,inference_steps=8,guidance_scale=1,chunked_decode=True,
                attention='upstream-chunked-halo-sdpa' if transformer.flash_attn_func is None else 'flash-attn',
                fallbacks=fallbacks,load_seconds=load_seconds,elapsed_seconds=time.monotonic()-started,
                peak_rss_gb=peak_rss/1024**3,reference_audio_used=False,output_processing={'normalization':False,'effects':False},**metrics)
except Exception as exc:
    result=dict(success=False,error_code=stage,error=str(exc),elapsed_seconds=time.monotonic()-started)
    traceback.print_exc()
finally:
    stop.set();gc.collect()
    if 'torch' in globals() and torch.cuda.is_available():torch.cuda.empty_cache()
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(0 if result.get('success') else 1)
