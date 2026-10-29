"""Compare F0 of the source vocal against the converted output.

If the model "cannot reach" high notes, the output F0 in the source's high
register will sit clearly below the source. If it merely sounds thin up there,
F0 will track fine and the problem is timbre, not pitch.
"""
import sys

import numpy as np
import soundfile as sf

SR = 16000
FRAME = 1024
HOP = 160
FMIN, FMAX = 65.0, 1300.0


def load(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def f0_track(x):
    lag_min, lag_max = int(SR / FMAX), int(SR / FMIN)
    win = np.hanning(FRAME).astype(np.float32)
    out = []
    for i in range(0, max(len(x) - FRAME, 1), HOP):
        fr = x[i:i + FRAME]
        if len(fr) < FRAME:
            break
        fr = fr * win
        if np.sqrt(np.mean(fr * fr)) < 5e-3:
            out.append(0.0)
            continue
        c = np.correlate(fr, fr, mode="full")[FRAME - 1:]
        seg = c[lag_min:lag_max + 1]
        if not len(seg) or seg.max() <= 0:
            out.append(0.0)
            continue
        lag = int(np.argmax(seg)) + lag_min
        thr = seg.max() * 0.6
        for k in range(lag, lag_max + 1):
            if c[k] >= thr:
                lag = k
                break
        out.append(SR / lag if lag > 0 else 0.0)
    return np.array(out, dtype=np.float32)


src_path, out_path = sys.argv[1], sys.argv[2]
a = f0_track(load(src_path))
b = f0_track(load(out_path))
n = min(len(a), len(b))
a, b = a[:n], b[:n]
both = (a > 0) & (b > 0)
print("frames: %d   both-voiced: %d (%.1f%%)  src-only: %d  out-only: %d"
      % (n, both.sum(), 100.0 * both.sum() / n, ((a > 0) & (b == 0)).sum(), ((a == 0) & (b > 0)).sum()))

if both.sum() < 50:
    raise SystemExit("not enough overlap")

sa, sb = a[both], b[both]
# fold obvious octave errors so the comparison is about the melody, not the estimator
ratio = sb / sa
folded = np.where(ratio > 1.45, ratio / 2, np.where(ratio < 0.69, ratio * 2, ratio))
print("pitch tracking: corr=%.3f  median ratio=%.3f (%.2f semitones)  within 1 semitone: %.1f%%"
      % (float(np.corrcoef(sa, sb)[0, 1]), float(np.median(folded)),
         12 * np.log2(max(float(np.median(folded)), 1e-6)),
         100.0 * float(np.mean(np.abs(12 * np.log2(np.maximum(folded, 1e-6))) < 1.0))))

print("\nby source register (does the output keep up where the source goes high?):")
edges = [(0, 250), (250, 350), (350, 450), (450, 550), (550, 700), (700, 1300)]
for lo, hi in edges:
    m = (sa >= lo) & (sa < hi)
    if m.sum() < 20:
        continue
    print("  src %4d-%4d Hz  n=%5d  src mean %6.1f  out mean %6.1f  shift %+5.1f Hz  %+5.2f st"
          % (lo, hi, m.sum(), sa[m].mean(), sb[m].mean(), sb[m].mean() - sa[m].mean(),
             12 * np.log2(max(sb[m].mean(), 1e-6) / max(sa[m].mean(), 1e-6))))
