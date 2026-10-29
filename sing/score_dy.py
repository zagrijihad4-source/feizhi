"""Score every dy_clean clip and emit quality-sorted lists for dataset curation."""
import glob
import json
import os

import librosa
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def score(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    r = librosa.feature.rms(y=y, hop_length=512)[0]
    db = 20 * np.log10(r + 1e-9)
    on = db > np.max(db) - 45
    d = db[on]
    dyn = float(np.percentile(d, 95) - np.percentile(d, 5))
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=512))
    flat = float(np.median(librosa.feature.spectral_flatness(S=S)[0]))
    f0 = librosa.yin(y, fmin=70, fmax=900, sr=sr, hop_length=512)
    v = f0[f0 > 0]
    return dict(
        f=os.path.basename(path),
        dyn=round(dyn, 2),
        flat=round(flat, 5),
        dur=round(len(y) / sr, 2),
        f0=round(float(np.median(v)), 1) if len(v) > 50 else 0.0,
    )


def main():
    rows = [score(p) for p in sorted(glob.glob(os.path.join(HERE, "source", "dy_clean", "*.wav")))]
    rows = [r for r in rows if r["f0"] > 0]
    rows.sort(key=lambda r: (-r["dyn"], r["flat"]))
    out = os.path.join(HERE, "outputs", "dy_quality.json")
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("scored", len(rows), "->", out)
    print(" dyn   flat    dur   f0   file")
    for r in rows[:12]:
        print(f"{r['dyn']:5.1f} {r['flat']:.5f} {r['dur']:5.1f} {r['f0']:5.0f}  {r['f']}")
    print(" ...")
    for th in (36, 34, 32, 30, 28, 26, 0):
        sel = [r for r in rows if r["dyn"] >= th]
        tot = sum(r["dur"] for r in sel)
        print(f"dyn >= {th:2d}: {len(sel):3d} clips  {tot:7.1f} s  {tot / 60:5.1f} min")


if __name__ == "__main__":
    main()
