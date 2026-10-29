"""截一段 8 秒人声，用于 RVC 实测（避免整首 3 分钟跑太久）。"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SRC = Path(r"<PROJECT_ROOT>\sing\source\sakura\wz_vocal_vocal.wav")
OUT = Path(r"<PROJECT_ROOT>\sing\outputs\_rvc_test_in.wav")

sys.stdout.reconfigure(encoding="utf-8")
x, sr = sf.read(str(SRC), dtype="float32", always_2d=True)
x = x.mean(axis=1)
n = int(sr * 8)
start = max(0, len(x) // 2 - n // 2)
seg = x[start:start + n]
peak = float(np.abs(seg).max()) or 1.0
sf.write(str(OUT), (seg / peak) * 0.9, sr)
print("src=%s sr=%d dur=%.2fs" % (SRC.name, sr, len(x) / sr))
print("out=%s dur=%.2fs peak=%.3f" % (OUT.name, len(seg) / sr, float(np.abs(seg).max())))
