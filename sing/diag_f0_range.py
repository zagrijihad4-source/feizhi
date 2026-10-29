"""Compare F0 ranges: training material vs the songs we convert.

If a song's pitch sits well above the training set's range, the model has no
reference timbre up there, which shows up as tone break-up. It does NOT change
which syllable gets sung -- that points at index-rate instead.
"""
import glob
import sys

import numpy as np
import soundfile as sf

SR = 16000
FRAME = 1024
HOP = 160
FMIN, FMAX = 65.0, 1200.0


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


def describe(name, f0):
    v = f0[f0 > 0]
    if not len(v):
        print("%-22s no voiced frames" % name)
        return None
    print("%-22s voiced %5.1f%%  p5 %6.1f  p50 %6.1f  p95 %6.1f  p99 %6.1f  max %6.1f" % (
        name, 100.0 * len(v) / len(f0), np.percentile(v, 5), np.percentile(v, 50),
        np.percentile(v, 95), np.percentile(v, 99), v.max()))
    return v


# training material: aggregate the slices of the model actually in use (yinyin)
train_files = sorted(glob.glob(r"<PROJECT_ROOT>\sing\RVC\logs\yinyin\0_gt_wavs\*.wav"))
allf = []
for f in train_files:
    allf.append(f0_track(load(f)))
train_v = np.concatenate([t[t > 0] for t in allf if len(t)]) if allf else np.array([])
describe("TRAIN yinyin (%d)" % len(train_files), np.concatenate(allf) if allf else train_v)

for p in sys.argv[1:]:
    describe(p.split("\\")[-1], f0_track(load(p)))

if len(train_v):
    lo, hi = np.percentile(train_v, 1), np.percentile(train_v, 99)
    print("\ntraining coverage (p1-p99): %.0f - %.0f Hz" % (lo, hi))
