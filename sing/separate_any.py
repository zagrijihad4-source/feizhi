"""Separate any audio file into vocals + accompaniment.

usage: python separate_any.py <input audio> <out_prefix> [der]
  out_prefix_vocal.wav / out_prefix_inst.wav
  der=1 enables the dereverb pass (cleaner but can thin the voice)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\sing\SoulX-Singer")

import numpy as np
import soundfile as sf

from preprocess.tools.vocal_separation.model import VocalSeparator

ROOT = Path(r"<PROJECT_ROOT>\sing\pretrained_models\SoulX-Singer-Preprocess")
src = Path(sys.argv[1])
prefix = sys.argv[2]
use_der = len(sys.argv) > 3 and sys.argv[3] == "1"

t0 = time.time()
sep = VocalSeparator(
    sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
    sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
    der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
    der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
    device="cuda",
    use_der=use_der,
    verbose=True,
)
print("model loaded %.1fs" % (time.time() - t0), flush=True)

t1 = time.time()
out = sep.process(str(src))
print("separated %.1fs sr=%s" % (time.time() - t1, out.sample_rate), flush=True)

voc = np.asarray(out.vocals)
acc = np.asarray(out.accompaniment)
if voc.ndim > 1:
    voc = voc.mean(axis=0) if voc.shape[0] < voc.shape[-1] else voc.mean(axis=-1)
if acc.ndim > 1:
    acc = acc.mean(axis=0) if acc.shape[0] < acc.shape[-1] else acc.mean(axis=-1)

vp = Path(prefix + "_vocal.wav")
ap = Path(prefix + "_inst.wav")
sr = int(out.sample_rate)
sf.write(str(vp), voc.astype(np.float32), sr)
sf.write(str(ap), acc.astype(np.float32), sr)
print("wrote %s (%.1fs) and %s (%.1fs)" % (vp, len(voc) / sr, ap, len(acc) / sr))
