"""Rank training clips by spectral bandwidth so quiet/reverby takes do not
drag the model's high band down.

usage: python dy_rank.py [dir]
Writes sorted list to dy_rank.txt and prints a summary.
"""
import pathlib
import sys

import numpy as np
import soundfile as sf

BANDS = [(0, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 12000), (12000, 16000)]


def analyze(path, target=44100):
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if len(x) < sr:
        return None
    if sr != target:
        n = int(round(len(x) * target / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    win = target * 3
    chunks = [(float(np.sqrt(np.mean(x[i:i + win] ** 2))), i) for i in range(0, max(len(x) - win, 1), win)]
    chunks = sorted([c for c in chunks if c[0] > 0.01], reverse=True)[:8]
    if not chunks:
        return None
    spec = np.zeros(1024 // 2 + 1)
    n = 0
    for _, s in chunks:
        seg = x[s:s + win]
        for k in range(0, len(seg) - 1024, 1024):
            spec += np.abs(np.fft.rfft(seg[k:k + 1024] * np.hanning(1024))) ** 2
            n += 1
    spec /= max(n, 1)
    freqs = np.fft.rfftfreq(1024, 1 / target)
    tot = spec.sum()
    if tot <= 0:
        return None
    cum = np.cumsum(spec) / tot
    roll95 = float(freqs[np.searchsorted(cum, 0.95)])
    centroid = float((freqs * spec).sum() / tot)
    b = {}
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        b["%d-%dk" % (lo // 1000, hi // 1000)] = 100.0 * spec[m].sum() / tot
    return roll95, centroid, b


d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"<PROJECT_ROOT>\sing\source\dy_train")
rows = []
for f in sorted(d.glob("*.wav")):
    r = analyze(f)
    if r:
        rows.append((r[0], r[1], f.stem, r[2]))

rows.sort(reverse=True)
out = d.parent / "dy_rank.txt"
out.write_text(
    "\n".join("%s\t%.0f\t%.0f" % (stem, roll95, cent) for roll95, cent, stem, _ in rows),
    encoding="utf8",
)

vals = [r[0] for r in rows]
print("clips: %d" % len(rows))
print("roll95: min %.0f  p25 %.0f  median %.0f  p75 %.0f  max %.0f" % (
    min(vals), np.percentile(vals, 25), np.median(vals), np.percentile(vals, 75), max(vals)))
for lo, hi, label in [(0, 2500, "<2500 闷"), (2500, 4000, "2500-4000 正常"), (4000, 99999, ">4000 亮")]:
    n = sum(1 for v in vals if lo <= v < hi)
    print("  %-14s %d" % (label, n))
print("\ntop 8:")
for roll95, cent, stem, b in rows[:8]:
    print("  %.0f  %s" % (roll95, stem))
print("bottom 8:")
for roll95, cent, stem, b in rows[-8:]:
    print("  %.0f  %s" % (roll95, stem))
print("-> %s" % out)
