"""Quick A/B analysis: loudness, voiced ratio, F0 track of two wav files."""
import sys

import numpy as np
import soundfile as sf

SR = 16000
FRAME = 1024
HOP = 160
FMIN, FMAX = 65.0, 1100.0


def load(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def f0_track(x):
    lag_min = int(SR / FMAX)
    lag_max = int(SR / FMIN)
    win = np.hanning(FRAME).astype(np.float32)
    out = []
    for i in range(0, max(len(x) - FRAME, 1), HOP):
        fr = x[i : i + FRAME]
        if len(fr) < FRAME:
            break
        fr = fr * win
        e = float(np.sqrt(np.mean(fr * fr)))
        if e < 5e-3:
            out.append(0.0)
            continue
        c = np.correlate(fr, fr, mode="full")[FRAME - 1 :]
        seg = c[lag_min : lag_max + 1]
        if not len(seg) or seg.max() <= 0:
            out.append(0.0)
            continue
        lag = int(np.argmax(seg)) + lag_min
        # sub-harmonic guard: prefer the shortest lag above 60% of the peak
        thr = seg.max() * 0.6
        for k in range(lag, lag_max + 1):
            if c[k] >= thr:
                lag = k
                break
        out.append(SR / lag if lag > 0 else 0.0)
    return np.array(out, dtype=np.float32)


def report(name, x):
    t = f0_track(x)
    voiced = t[t > 0]
    print("%-10s dur=%5.2fs peak=%.3f rms=%.4f voiced=%5.1f%%" % (name, len(x) / SR, np.abs(x).max(), np.sqrt(np.mean(x * x)), 100.0 * len(voiced) / max(len(t), 1)))
    if len(voiced):
        print("%-10s F0 mean=%.1fHz  median=%.1fHz  p5=%.1f  p95=%.1f" % (name, voiced.mean(), np.median(voiced), np.percentile(voiced, 5), np.percentile(voiced, 95)))
    return t


a = load(sys.argv[1])
b = load(sys.argv[2])
ta = report("source", a)
tb = report("converted", b)

n = min(len(ta), len(tb))
ma = (ta[:n] > 0) & (tb[:n] > 0)
if ma.sum() > 10:
    r = float(np.corrcoef(ta[:n][ma], tb[:n][ma])[0, 1])
    ratio = float(np.median(tb[:n][ma] / np.maximum(ta[:n][ma], 1e-6)))
    print("overlap voiced frames=%d  F0 corr=%.3f  median ratio=%.3f (%.1f semitones)" % (ma.sum(), r, ratio, 12 * np.log2(max(ratio, 1e-6))))
    # octave-corrected correlation: fold each frame ratio into [0.7, 1.4] first
    rr = tb[:n][ma] / np.maximum(ta[:n][ma], 1e-6)
    rr = np.where(rr > 1.45, rr / 2.0, np.where(rr < 0.7, rr * 2.0, rr))
    corr_fix = float(np.corrcoef(ta[:n][ma] * rr, tb[:n][ma])[0, 1])
    print("octave-corrected F0 corr=%.3f  (median rr=%.3f)" % (corr_fix, float(np.median(rr))))
else:
    print("not enough overlapping voiced frames: %d" % ma.sum())

# loudness envelope: timing evidence independent of timbre
m = min(len(a), len(b))
k = int(0.05 * SR)
ne = m // k
if ne > 20:
    ea = np.array([np.sqrt(np.mean(a[i * k : (i + 1) * k] ** 2)) for i in range(ne)])
    eb = np.array([np.sqrt(np.mean(b[i * k : (i + 1) * k] ** 2)) for i in range(ne)])
    print("envelope corr=%.3f over %d frames (50ms)" % (float(np.corrcoef(ea, eb)[0, 1]), ne))
