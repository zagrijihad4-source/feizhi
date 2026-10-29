"""Separate all 19 source recordings into clean vocals + accompaniment.

The loopback recordings in source/batch carry the full system mix, so every
training set built from them taught the model the accompaniment too. This
produces source/clean_vocals/*.wav which rebuild_trainset.py can consume.
"""
import os
import sys
import time
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
sys.path.insert(0, str(SING / "SoulX-Singer"))

import numpy as np
import soundfile as sf

from preprocess.tools.vocal_separation.model import VocalSeparator

ROOT = SING / "pretrained_models" / "SoulX-Singer-Preprocess"
SRC = SING / "source" / "batch"
OUT = SING / "source" / "clean_vocals"
OUT.mkdir(parents=True, exist_ok=True)

files = sorted(SRC.glob("yy_*.wav"))
print("sources: %d" % len(files), flush=True)

t0 = time.time()
sep = VocalSeparator(
    sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
    sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
    der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
    der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
    device="cuda",
    use_der=False,
    verbose=False,
)
print("model loaded %.1fs" % (time.time() - t0), flush=True)

rows = []
for i, f in enumerate(files, 1):
    dst = OUT / f.name
    if dst.exists() and dst.stat().st_size > 10000:
        print("  [%2d/%d] %-12s skip (already done)" % (i, len(files), f.name), flush=True)
        continue
    t1 = time.time()
    out = sep.process(str(f))
    voc = np.asarray(out.vocals)
    if voc.ndim > 1:
        voc = voc.mean(axis=0) if voc.shape[0] < voc.shape[-1] else voc.mean(axis=-1)
    voc = voc.astype(np.float32)
    sr = int(out.sample_rate)
    sf.write(str(dst), voc, sr, subtype="PCM_16")
    # 分离前后能量对比：伴奏残留越低，人声占比越高
    x0, sr0 = sf.read(str(f), dtype="float32", always_2d=True)
    r0 = float(np.sqrt(np.mean(x0.mean(axis=1) ** 2)))
    rv = float(np.sqrt(np.mean(voc ** 2)))
    rows.append((f.name, len(voc) / sr, r0, rv, rv / max(r0, 1e-9)))
    print("  [%2d/%d] %-12s %.1fs  orig_rms %.4f -> vocal_rms %.4f (%.2fx)  %.1fs"
          % (i, len(files), f.name, len(voc) / sr, r0, rv, rv / max(r0, 1e-9), time.time() - t1), flush=True)

print("\n=== summary ===")
ratios = [r[4] for r in rows]
print("files %d   total %.1fs   vocal/orig rms ratio  min %.2f  mean %.2f  max %.2f"
      % (len(rows), sum(r[1] for r in rows), min(ratios), float(np.mean(ratios)), max(ratios)))
print("-> %s" % OUT)
