"""Compress the converted vocal down to the singer's own dynamics.

Measured on her real 沦陷 clip: 26.1 dB of loudness range. The model output
sits at 37.4 dB, i.e. it exaggerates the swells far beyond what she actually
sings, which reads as unnatural emotion rather than more of it. A gentle
downward compressor pulls the peak-to-valley span back toward her reference.

usage: python match_dynamics.py <in.wav> <out.wav> <target_db> [ratio]
"""
import sys

import librosa
import numpy as np
import soundfile as sf


def range_db(x, sr, hop=512):
    r = librosa.feature.rms(y=x.astype("float32"), hop_length=hop)[0]
    db = 20 * np.log10(r + 1e-9)
    on = db > np.max(db) - 45
    d = db[on]
    return float(np.percentile(d, 95) - np.percentile(d, 5)), float(np.percentile(d, 95)), float(np.percentile(d, 5))


def compress(x, sr, ratio=3.0, thresh_offset=-12.0, smooth_ms=12.0, makeup=True):
    """Frame-wise downward compression on a smoothed envelope."""
    w = max(1, int(sr * smooth_ms / 1000.0))
    env = librosa.feature.rms(y=x.astype("float32"), frame_length=2 * w, hop_length=w)[0]
    db = 20 * np.log10(env + 1e-9)
    thr = np.max(db) + thresh_offset
    over = np.maximum(0.0, db - thr)
    gain_db = -(ratio - 1.0) / ratio * over
    if makeup:
        gain_db -= np.min(gain_db) * 0.35
    # upsample the gain curve to sample rate
    frames = np.arange(len(x)) / w
    g = np.interp(frames, np.arange(len(gain_db)), gain_db)
    # smooth the applied gain to avoid pumping
    k = np.ones(w) / w
    g = np.convolve(g, k, mode="same")
    return x * np.power(10.0, g / 20.0)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    target = float(sys.argv[3]) if len(sys.argv) > 3 else 26.0
    ratio = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0

    y, sr = sf.read(src, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    r0, h0, l0 = range_db(y, sr)
    print("before: range=%.1f dB  (p95 %.1f .. p5 %.1f)" % (r0, h0, l0))

    best = y
    best_err = abs(r0 - target)
    for r in (ratio, ratio * 0.7, ratio * 1.5, 2.0, 4.0, 6.0):
        for off in (-8.0, -12.0, -16.0, -20.0):
            c = compress(y, sr, ratio=r, thresh_offset=off)
            rr, _, _ = range_db(c, sr)
            if abs(rr - target) < best_err:
                best_err = abs(rr - target)
                best = c
                print("  ratio=%.1f thresh=%+.0f -> %.1f dB" % (r, off, rr))

    peak = np.max(np.abs(best)) + 1e-9
    best = best / peak * 0.95
    sf.write(dst, best.astype("float32"), sr)
    r1, h1, l1 = range_db(best, sr)
    print("after : range=%.1f dB  (p95 %.1f .. p5 %.1f)  target %.1f" % (r1, h1, l1, target))
    print("wrote", dst)


if __name__ == "__main__":
    main()
