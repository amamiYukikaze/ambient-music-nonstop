"""One isolated inference job; GPU/host memory is reclaimed when this process exits."""
import gc
import json
import os
import sys
import time
import traceback
import threading
from worker_watchdog import start as start_watchdog
start_watchdog()
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.models import MODELS
sys.path.insert(0, str(ROOT / 'vendor/ACE-Step-1.5'))
request = json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
out = Path(request['output'])
out.mkdir(parents=True, exist_ok=True)
lm_enabled=bool(request.get('lm_enabled',False))
os.environ.update(ACESTEP_INIT_LLM='true' if lm_enabled else 'false', MAX_CUDA_VRAM='6', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
started = time.monotonic()
import psutil
peak_rss=0
monitor_stop=threading.Event()
def monitor():
    global peak_rss
    process=psutil.Process()
    while not monitor_stop.wait(.3):
        peak_rss=max(peak_rss,process.memory_info().rss)
threading.Thread(target=monitor,daemon=True).start()
stage = 'model_load_error'
result = {}
try:
    variant=request.get('model_variant','acestep-v15-turbo');spec=MODELS[variant]
    import torch
    import psutil
    torch.set_num_threads(6)
    free,total = torch.cuda.mem_get_info()
    budget = min(float(request.get('vram_gb',6.5))*1024**3,free-400*1024**2)
    torch.cuda.set_per_process_memory_fraction(max(.25,budget/total))
    torch.cuda.reset_peak_memory_stats()
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music
    from acestep.llm_inference import LLMHandler
    handler = AceStepHandler()
    status,ok = handler.initialize_service(
        project_root=str(Path(request['model_root'])), config_path=variant,
        device='cuda', use_flash_attention=False, compile_model=False,
        offload_to_cpu=True, offload_dit_to_cpu=True, quantization='int8_weight_only')
    if not ok:
        raise RuntimeError(status)
    stage='generation_error'
    # The official encoder truncates the entire instruction/caption/metas at 256.
    # Refuse an overlong request instead of silently discarding key/BPM at its end.
    from acestep.constants import SFT_GEN_PROMPT, DEFAULT_DIT_INSTRUCTION
    meta_text=(f'- bpm: {request["bpm"]}\n- timesignature: {request.get("timesignature","4")}\n'
               f'- keyscale: {request["key"]}\n- duration: {request["duration"]} seconds\n')
    text_tokens=len(handler.text_tokenizer.encode(SFT_GEN_PROMPT.format(DEFAULT_DIT_INSTRUCTION,request['prompt'],meta_text)))
    if text_tokens>256:raise ValueError(f'conditioning_text_too_long: {text_tokens} tokens > 256; shorten caption')
    stage='model_load_error'
    llm=LLMHandler()
    if lm_enabled:
        status,ok=llm.initialize(checkpoint_dir=str(Path(request['model_root'])/'checkpoints'),lm_model_path='acestep-5Hz-lm-0.6B',backend='pt',device='cuda',offload_to_cpu=True)
        if not ok:raise RuntimeError(status)
    load_seconds=time.monotonic()-started
    stage='generation_error'
    params=GenerationParams(caption=request['prompt'],lyrics='[Instrumental]',instrumental=True,
        bpm=request['bpm'],keyscale=request['key'],timesignature=request.get('timesignature','4'),duration=request['duration'],
        seed=request['seed'],inference_steps=spec['steps'],shift=request.get('shift',1.0),guidance_scale=spec['guidance'],thinking=lm_enabled,use_cot_caption=False,
        use_cot_metas=False,use_cot_language=False,enable_normalization=False,
        fade_in_duration=request.get('fade_in_duration',.05),fade_out_duration=request.get('fade_out_duration',.1))
    config=GenerationConfig(batch_size=1,use_random_seed=False,seeds=[request['seed']],audio_format='wav')
    generation=generate_music(handler,llm,params,config,save_dir=str(out))
    if not generation.success or not generation.audios:
        raise RuntimeError(generation.error or generation.status_message)
    audio=generation.audios[0]
    result=dict(success=True,path=audio['path'],sample_rate=audio['sample_rate'],
        model=spec['name'],model_variant=variant,model_revision=spec['revision'],
        source_revision='ca1e85fe9430179831e6bc6be790c332190a3866',
        inference_steps=spec['steps'],conditioning_tokens=text_tokens,shift=request.get('shift',1.0),guidance_scale=spec['guidance'],lm_enabled=lm_enabled,lm_model='acestep-5Hz-lm-0.6B' if lm_enabled else None,lm_revision='148d8ea0225bdab342ee1ae3a354275ccd60ca80' if lm_enabled else None,lm_backend='pt' if lm_enabled else None,quantization=handler.quantization,load_seconds=load_seconds,
        output_processing={'normalization':False,'fade_in_seconds':params.fade_in_duration,'fade_out_seconds':params.fade_out_duration},reference_audio_used=False,
        elapsed_seconds=time.monotonic()-started,peak_vram_gb=torch.cuda.max_memory_allocated()/1024**3,
        peak_reserved_gb=torch.cuda.max_memory_reserved()/1024**3,
        rss_gb=psutil.Process().memory_info().rss/1024**3,peak_rss_gb=peak_rss/1024**3,
        torch_version=torch.__version__,budget_vram_gb=budget/1024**3)
except Exception as exc:
    message=str(exc)
    code='cuda_oom' if ('out of memory' in message.lower() or 'cuda error' in message.lower() and 'memory' in message.lower()) else stage
    result=dict(success=False,error_code=code,error=message,elapsed_seconds=time.monotonic()-started)
    traceback.print_exc()
finally:
    monitor_stop.set()
    gc.collect()
    if 'torch' in globals() and torch.cuda.is_available():
        torch.cuda.empty_cache()
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(0 if result.get('success') else 1)
