"""Re-measure F0 with rmvpe (the same extractor RVC itself uses) instead of
autocorrelation, which mis-locks onto harmonics once the timbre changes.

usage: python diag_f0_rmvpe.py <src.wav> <out.wav>
"""
import os
import sys

import numpy as np
import soundfile as sf

RVC = r"<PROJECT_ROOT>\sing\RVC"
sys.path.insert(0, RVC)
os.chdir(RVC)
os.environ.setdefault("rmvpe_root", os.path.join(RVC, "assets", "rmvpe"))

import torch  # noqa: E402
from infer.rmvpe import RMVPE  # noqa: E402

SR = 16000


def load16k(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


model = RMVPE(os.path.join(RVC, "assets", "rmvpe", "rmvpe.pt"), is_half=False, device="cuda")

src_path, out_path = sys.argv[1], sys.argv[2]
for label, path in (("source", src_path), ("output", out_path)):
    x = load16k(path)
    f0 = model.infer_from_audio(x, thred=0.03)
    f0 = np.asarray(f0, dtype=np.float32)
    v = f0[f0 > 0]
    print("%-7s frames=%5d voiced=%5.1f%%  p5 %6.1f  p50 %6.1f  p95 %6.1f  p99 %6.1f"
          % (label, len(f0), 100.0 * len(v) / max(len(f0), 1),
             np.percentile(v, 5), np.percentile(v, 50), np.percentile(v, 95), np.percentile(v, 99)))
    globals()[label] = f0

a, b = source, output
n = min(len(a), len(b))
a, b = a[:n], b[:n]
both = (a > 0) & (b > 0)
sa, sb = a[both], b[both]
ratio = sb / sa
print("\nboth-voiced %d  median ratio=%.3f (%.2f semitones)  within 1 semitone %.1f%%"
      % (both.sum(), float(np.median(ratio)), 12 * np.log2(max(float(np.median(ratio)), 1e-6)),
         100.0 * float(np.mean(np.abs(12 * np.log2(np.maximum(ratio, 1e-6))) < 1.0))))

print("\nby source register:")
for lo, hi in [(0, 250), (250, 350), (350, 450), (450, 550), (550, 700), (700, 1300)]:
    m = (sa >= lo) & (sa < hi)
    if m.sum() < 20:
        continue
    print("  src %4d-%4d Hz  n=%5d  src %6.1f  out %6.1f  %+5.2f st"
          % (lo, hi, m.sum(), sa[m].mean(), sb[m].mean(),
             12 * np.log2(max(sb[m].mean(), 1e-6) / max(sa[m].mean(), 1e-6))))
