"""Band-energy comparison: where does the "bad recording" come from?"""
import sys

import numpy as np
import soundfile as sf

BANDS = [(0, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 12000), (12000, 16000), (16000, 20000)]


def load(path, target=44100):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != target:
        n = int(round(len(x) * target / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def bands(path):
    x = load(path)
    # analyse only the loudest 60 s so quiet gaps do not skew the spectrum
    win = 44100 * 5
    chunks = [(float(np.sqrt(np.mean(x[i : i + win] ** 2))), i) for i in range(0, max(len(x) - win, 1), win)]
    chunks = [c for c in chunks if c[0] > 0.01]
    chunks.sort(reverse=True)
    picks = [i for _, i in chunks[:12]]
    if not picks:
        return None
    spec = np.zeros(2048 // 2 + 1)
    n = 0
    for s in picks:
        seg = x[s : s + win]
        for k in range(0, len(seg) - 2048, 2048):
            spec += np.abs(np.fft.rfft(seg[k : k + 2048] * np.hanning(2048))) ** 2
            n += 1
    spec /= max(n, 1)
    freqs = np.fft.rfftfreq(2048, 1 / 44100)
    tot = spec.sum()
    out = []
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out.append(100.0 * spec[m].sum() / tot if tot > 0 else 0.0)
    # spectral centroid + rolloff: single numbers that track "air / clarity"
    centroid = float((freqs * spec).sum() / tot) if tot > 0 else 0.0
    cum = np.cumsum(spec) / tot if tot > 0 else np.zeros_like(spec)
    rolloff = float(freqs[np.searchsorted(cum, 0.95)]) if tot > 0 else 0.0
    return out, centroid, rolloff


print("%-24s %s  %7s %7s" % ("file", "  ".join("%5s" % ("%d-%dk" % (a // 1000, b // 1000)) for a, b in BANDS), "centr", "roll95"))
for path in sys.argv[1:]:
    r = bands(path)
    name = path.split("\\")[-1]
    if not r:
        print("%-24s silent" % name)
        continue
    out, cent, roll = r
    print("%-24s %s  %7.0f %7.0f" % (name, "  ".join("%5.1f" % v for v in out), cent, roll))
