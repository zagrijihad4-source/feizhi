"""把《潮汐》分离成人声 + 伴奏，存成 wav。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\sing\SoulX-Singer")

import numpy as np
import soundfile as sf

from preprocess.tools.vocal_separation.model import VocalSeparator

ROOT = Path(r"<PROJECT_ROOT>\sing\pretrained_models\SoulX-Singer-Preprocess")
SRC = Path(r"<PROJECT_ROOT>\sing\source\taoxi.wav")
OUT = Path(r"<PROJECT_ROOT>\sing\source")

t0 = time.time()
sep = VocalSeparator(
    sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
    sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
    der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
    der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
    device="cuda",
    use_der=False,
    verbose=True,
)
print("模型加载 %.1fs" % (time.time() - t0), flush=True)

t1 = time.time()
out = sep.process(str(SRC))
print("分离完成 %.1fs  sr=%s" % (time.time() - t1, out.sample_rate), flush=True)

voc = np.asarray(out.vocals)
acc = np.asarray(out.accompaniment)
if voc.ndim > 1:
    voc = voc.mean(axis=0) if voc.shape[0] < voc.shape[-1] else voc.mean(axis=-1)
if acc.ndim > 1:
    acc = acc.mean(axis=0) if acc.shape[0] < acc.shape[-1] else acc.mean(axis=-1)
print("vocals", voc.shape, "acc", acc.shape, "sr", out.sample_rate)

vp = OUT / "taoxi_vocal.wav"
ap = OUT / "taoxi_inst.wav"
sf.write(str(vp), voc, int(out.sample_rate))
sf.write(str(ap), acc, int(out.sample_rate))
print("写出:", vp, "%.1f MB" % (vp.stat().st_size / 1048576))
print("写出:", ap, "%.1f MB" % (ap.stat().st_size / 1048576))
