"""Verify the claims in the external diagnosis against the actual files.

1) does voice.wav really have discontinuities at each 10 s join?
2) where do the three slices actually come from?
3) is the slice gain a plain constant (normalisation) or something else?
"""
import os

import numpy as np
import soundfile as sf

V = r"<PROJECT_ROOT>\sing\RVC\dataset\yinyin\voice.wav"
S = r"<PROJECT_ROOT>\sing\RVC\logs\yinyin\0_gt_wavs"

v, sr = sf.read(V, dtype="float32", always_2d=True)
v = v.mean(axis=1)
d = np.abs(np.diff(v))
p985 = float(np.percentile(d, 98.5))
print("voice.wav  %.3fs @ %d Hz   |diff| p98.5 = %.5f   max = %.5f" % (len(v) / sr, sr, p985, d.max()))

print("\n-- discontinuity scan at each 10 s join --")
for t in range(10, int(len(v) / sr), 10):
    i = int(t * sr)
    win = d[max(0, i - 40):i + 40]
    flag = "  <-- JUMP" if win.max() > p985 else ""
    print("  t=%3ds  local max |diff| = %.5f  (p98.5=%.5f)%s" % (t, win.max(), p985, flag))

print("\n-- slice origin and gain (resampled to a common rate first) --")
from scipy import signal as _sig


def rs(x, a, b):
    if a == b:
        return x
    from math import gcd
    g = gcd(int(a), int(b))
    return _sig.resample_poly(x, b // g, a // g).astype(np.float32)


v40 = rs(v, sr, 40000)
for name in ("0_0.wav", "0_1.wav", "0_10.wav"):
    p = os.path.join(S, name)
    y, ysr = sf.read(p, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    y40 = rs(y, ysr, 40000)
    if len(y40) >= len(v40):
        print("  %s longer than source?" % name)
        continue
    c = _sig.correlate(v40, y40, mode="valid", method="fft")
    best = int(np.argmax(np.abs(c)))
    seg = v40[best:best + len(y40)]
    gain = float(np.linalg.norm(y40) / max(np.linalg.norm(seg), 1e-9))
    r = float(np.corrcoef(y40, seg)[0, 1])
    print("  %-9s %.2fs  -> voice.wav(40k) %6.2f-%6.2f s   corr=%.4f  energy ratio=%.3f"
          % (name, len(y40) / 40000, best / 40000, (best + len(y40)) / 40000, r, gain))
