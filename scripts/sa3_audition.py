"""Isolated SA3 auditions. No library insertion, style gate or audio effects."""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/stable-audio-3'))
os.environ.setdefault('ENABLE_TORCH_COMPILE', '0')
MODEL_REVISION = '27b5a21b791b1b033d193a9e1e3ce78493f102f9'
CODE_REVISION = '779434a908193105335fd8d833418603625b2859'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


@contextmanager
def audition_lease(wait_seconds=0):
    from server.locks import InferenceLease
    deadline=time.monotonic()+wait_seconds
    while True:
        lease=InferenceLease()
        try:lease.__enter__();break
        except BlockingIOError:
            if time.monotonic()>=deadline:raise
            time.sleep(.5)
    try:yield
    finally:lease.__exit__(None,None,None)


def render(core, cfg, item, duration, device, record):
    import torch
    from stable_audio_3 import StableAudioModel
    cuda = device == 'cuda'
    dtype = torch.float16 if cuda else torch.float32
    core.model.to(device='cpu', dtype=dtype)
    core.pretransform.to(device='cpu', dtype=dtype)
    model = StableAudioModel(core, cfg, device, cuda)
    record.update(device=device, inference_dtype=str(dtype))
    t0 = time.perf_counter()
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    try:
        conditioning = [{'prompt':item['prompt'], 'seconds_total':duration}]
        print(f"stage: conditioning {item['id']} ({device})", flush=True)
        with torch.inference_mode():
            tensors = core.conditioner(conditioning, 'cpu')
            tensors = {k:[v.to(device) if v is not None else None for v in values] for k,values in tensors.items()}
            print(f"stage: diffusion {item['id']} ({device})", flush=True)
            core.model.to(device)
            latents = model.generate(conditioning=conditioning, conditioning_tensors=tensors,
                                     duration=duration, steps=8, cfg_scale=1.0,
                                     sample_size=cfg['sample_size'],
                                     seed=item['seed'], batch_size=1, return_latents=True,
                                     chunked_decode=True)
            if cuda:
                torch.cuda.synchronize()
            record['diffusion_and_conditioning_seconds'] = time.perf_counter()-t0
            core.model.to('cpu')
            del tensors
            gc.collect()
            if cuda:
                torch.cuda.empty_cache()
            print(f"stage: chunked_decode {item['id']} ({device})", flush=True)
            core.pretransform.to(device)
            audio = core.pretransform.decode(latents.to(dtype), chunked=True)
            audio = audio[0, :, :int(duration*cfg['sample_rate'])].float().cpu().numpy().T
            if cuda:
                torch.cuda.synchronize()
                record['peak_cuda_allocated_bytes'] = torch.cuda.max_memory_allocated()
                record['peak_cuda_reserved_bytes'] = torch.cuda.max_memory_reserved()
            return audio
    finally:
        core.model.to('cpu')
        core.pretransform.to('cpu')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--prompts', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--duration', type=float, default=90)
    p.add_argument('--device', choices=['auto', 'cuda', 'cpu'], default='auto', help='auto retries on CPU after CUDA OOM')
    p.add_argument('--only', choices=['1', '2'])
    p.add_argument('--check', action='store_true', help='Check imports, files and prompt token counts only')
    p.add_argument('--lease-wait-seconds',type=int,default=0,help='Wait for existing production inference without interrupting playback')
    args = p.parse_args()
    if not 1 <= args.duration <= 380:
        p.error('duration must be between 1 and 380 seconds')
    args.output.mkdir(parents=True, exist_ok=True)
    import torch
    import psutil
    import soundfile as sf
    from stable_audio_3 import StableAudioModel
    from stable_audio_3.loading_utils import load_diffusion_cond
    from stable_audio_3.models import transformer
    from transformers import AutoTokenizer
    from server.locks import InferenceLease

    # Upstream includes a bounded sliding-window SDPA fallback. Windows has no
    # supported Triton in this environment: bypass repeated failed compile attempts.
    if sys.platform == 'win32':
        transformer.flex_attention_available = False
        transformer.flex_attention_compiled = None
    attention = 'flash-attn' if transformer.flash_attn_func is not None else 'upstream-chunked-halo-sdpa'
    from source_revision import revision
    repo_revision = revision(ROOT/'vendor/stable-audio-3')
    if repo_revision != CODE_REVISION:
        raise RuntimeError('SA3 source changed; re-verify the adapter against the new version')
    for filename in ['model_config.json', 'model.safetensors', 't5gemma-b-b-ul2/config.json', 't5gemma-b-b-ul2/model.safetensors']:
        if not (args.model_dir / filename).is_file():
            raise FileNotFoundError(f'Model download incomplete: {filename}')
    cfg = json.loads((args.model_dir/'model_config.json').read_text(encoding='utf-8'))
    for item in cfg['model']['conditioning']['configs']:
        if item['type'] == 't5gemma':
            item['config']['model_path'] = str(args.model_dir.resolve())
    prompts = json.loads(args.prompts.read_text(encoding='utf-8'))
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), subfolder='t5gemma-b-b-ul2', local_files_only=True)
    for item in prompts:
        item['prompt_tokens'] = len(tokenizer(item['prompt'])['input_ids'])
        if item['prompt_tokens'] > 256:
            raise ValueError(f"Prompt would be truncated: {item['id']} ({item['prompt_tokens']})")
    device = 'cuda' if args.device == 'auto' and torch.cuda.is_available() else ('cpu' if args.device == 'auto' else args.device)
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA explicitly requested but unavailable')
    print(json.dumps({'stage':'preflight', 'torch':torch.__version__, 'device':device, 'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None, 'attention':attention, 'prompts':[{k:x[k] for k in ['id','prompt_tokens']} for x in prompts]}, ensure_ascii=False), flush=True)
    if args.check:
        return
    torch.set_num_threads(6)
    process = psutil.Process()
    ram = {'peak_rss_bytes':0}
    stop = threading.Event()
    def monitor():
        while not stop.wait(.25):
            ram['peak_rss_bytes'] = max(ram['peak_rss_bytes'], process.memory_info().rss)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    results = []
    started = time.perf_counter()
    try:
        with audition_lease(args.lease_wait_seconds):
            if device == 'cuda':
                torch.cuda.set_per_process_memory_fraction(6.5 * 1024**3 / torch.cuda.get_device_properties(0).total_memory)
            print('stage: model_load_cpu_fp16', flush=True)
            # Instantiate directly in FP16 on CPU to avoid the upstream loader's
            # temporary full-FP32 GPU copy. Text encoder remains CPU-resident.
            previous_dtype = torch.get_default_dtype()
            try:
                torch.set_default_dtype(torch.float16)
                core = load_diffusion_cond(cfg, str(args.model_dir/'model.safetensors'), device='cpu', model_half=True)
            finally:
                torch.set_default_dtype(previous_dtype)
            core.conditioner.float()
            core.conditioner.conditioners['prompt'].model.float()
            load_seconds = time.perf_counter() - started
            for item in prompts:
                if args.only and item['id'] != args.only:
                    continue
                record = {**item, 'model':'stable-audio-3-medium', 'model_revision':MODEL_REVISION,
                          'code_revision':repo_revision, 'duration_requested':args.duration,
                          'steps':8, 'cfg_scale':1, 'batch_size':1, 'attention':attention,
                          'chunked_decode':True, 'text_encoder_device':'cpu', 'staged_gpu_offload':True,
                          'qc':'bypassed_for_audition', 'postprocessing':'none',
                          'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'load_seconds':load_seconds}
                t0 = time.perf_counter()
                stage = 'conditioning'
                try:
                    stage = 'generation'
                    retry_cpu = False
                    try:
                        audio = render(core, cfg, item, args.duration, device, record)
                    except torch.cuda.OutOfMemoryError:
                        if args.device != 'auto' or device != 'cuda':
                            raise
                        record['fallback'] = {'reason':'cuda_oom', 'from':'cuda', 'to':'cpu'}
                        write_json(args.output/f"{item['id']}-cuda-oom.json", record)
                        retry_cpu = True
                    if retry_cpu:
                        # Retry outside the except block so its traceback no longer
                        # retains GPU tensors from the failed forward pass.
                        gc.collect()
                        torch.cuda.empty_cache()
                        device = 'cpu'
                        print('stage: cuda_oom_recovered_retry_cpu', flush=True)
                        audio = render(core, cfg, item, args.duration, device, record)
                    stage = 'save'
                    target = args.output/f"{item['id']}-{item['slug']}.wav"
                    sf.write(str(target), audio, cfg['sample_rate'], subtype='FLOAT')
                    # Descriptive measurements only; never reject/regenerate by QC.
                    import numpy as np
                    record.update(status='done', path=str(target.resolve()), sample_rate=cfg['sample_rate'],
                                  channels=audio.shape[1], duration=len(audio)/cfg['sample_rate'],
                                  finite=bool(np.isfinite(audio).all()), sample_peak=float(np.max(np.abs(audio))),
                                  rms=float(np.sqrt(np.mean(audio.astype('float64')**2))),
                                  elapsed_seconds=time.perf_counter()-t0, **ram)
                    del audio
                except Exception as exc:
                    record.update(status='failed', stage=stage,
                                  error_type='cuda_oom' if isinstance(exc, torch.cuda.OutOfMemoryError) else 'generation_error',
                                  exception_type=type(exc).__name__, message=str(exc), elapsed_seconds=time.perf_counter()-t0)
                    traceback.print_exc()
                    core.model.to('cpu')
                    core.pretransform.to('cpu')
                    gc.collect()
                    torch.cuda.empty_cache()
                results.append(record)
                write_json(args.output/f"{item['id']}-{item['slug']}.json", record)
                write_json(args.output/'run.json', {'results':results, **ram})
                print(json.dumps(record, ensure_ascii=False), flush=True)
            playlist = ['#EXTM3U']
            for record in results:
                if record['status'] == 'done':
                    playlist += [f"#EXTINF:{int(record['duration'])},{record['title']}", record['path']]
            (args.output/'SA3试听.m3u8').write_text('\n'.join(playlist)+'\n', encoding='utf-8-sig')
    except Exception as exc:
        write_json(args.output/'failure.json', {'error_type':'model_load_error', 'exception_type':type(exc).__name__, 'message':str(exc), **ram})
        raise
    finally:
        stop.set()
        thread.join(timeout=2)
    if any(x['status'] != 'done' for x in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
