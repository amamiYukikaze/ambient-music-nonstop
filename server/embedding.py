"""CPU CLAP semantics plus acoustic signatures; similarity is not musical identity."""
import numpy as np
from .config import DATA,model_root
from .qc import decode, probe

CLAP_REVISION = '8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a'


def features(path):
    import torch
    from transformers import ClapModel, ClapProcessor
    import librosa
    torch.set_num_threads(4)
    model_path = model_root('clap')
    # An unavailable embedding model is an explicit processing error, never a silent pass.
    model = ClapModel.from_pretrained(model_path,local_files_only=True).eval()
    processor = ClapProcessor.from_pretrained(model_path,local_files_only=True)
    duration=probe(path)['duration']
    clips=[decode(path,48000,start=max(0,(duration-10)*p),duration=10).mean(axis=1).copy() for p in [.15,.5,.85]]
    with torch.inference_mode():
        inputs=processor(audio=clips,sampling_rate=48000,return_tensors='pt',padding=True)
        emb=model.get_audio_features(**inputs).numpy()
    emb/=np.maximum(np.linalg.norm(emb,axis=1,keepdims=True),1e-9)
    vector=emb.mean(axis=0)
    vector/=max(np.linalg.norm(vector),1e-9)
    mono=decode(path,12000).mean(axis=1)
    # Downsampled chroma timeline retains changes ignored by pooled CLAP vectors.
    chroma=librosa.feature.chroma_stft(y=mono,sr=12000,hop_length=1024)
    signature=np.stack([c.mean(axis=1) for c in np.array_split(chroma,64,axis=1)],axis=1)
    signature/=np.maximum(np.linalg.norm(signature,axis=0,keepdims=True),1e-8)
    tempo=librosa.feature.tempo(y=mono,sr=12000,hop_length=512)
    centroid=float(librosa.feature.spectral_centroid(y=mono,sr=12000).mean())
    return vector.astype('<f4'),signature.astype('<f4'),dict(embedding_model='laion/clap-htsat-unfused',embedding_revision=CLAP_REVISION,embedding_windows=[.15,.5,.85],bpm_estimated=float(tempo[0]),bpm_estimate_note='half/double ambiguity; requested tempo remains separate',spectral_centroid_hz=centroid)


def compare(vector, signature, candidates):
    nearest=None
    for c in candidates:
        if c['embedding'] is None or c['fingerprint'] is None:
            continue
        similarity=float(vector @ np.frombuffer(c['embedding'],dtype='<f4'))
        other=np.frombuffer(c['fingerprint'],dtype='<f4').reshape(12,64)
        acoustic=float(np.sum(signature*other,axis=0).mean())
        if nearest is None or similarity>nearest['cosine']:
            nearest=dict(track_id=c['id'],cosine=similarity,chroma_similarity=acoustic)
        # High CLAP similarity alone mostly means same genre/timbre, so require both.
        if similarity>.985 and acoustic>.98:
            return True,dict(track_id=c['id'],cosine=similarity,chroma_similarity=acoustic)
    return False,nearest
