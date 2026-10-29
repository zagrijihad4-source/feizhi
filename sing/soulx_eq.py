"""Frequency shaping for the SoulX cover.

Measured against the source stem: the converter is balanced except for a
2.3-2.5 dB shortfall above 8 kHz (air / breath) and a slightly muddy
250-500 Hz region inherited from the separation. This applies three gentle
peaking filters rather than a broad tilt, so timbre stays intact.
"""
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import sosfiltfilt, iirpeak, tf2sos

# (centre Hz, gain dB, Q)
DEFAULT_CURVE = [
    (350.0, -1.2, 1.0),
    (3000.0, 1.6, 1.4),
    (9500.0, 2.4, 0.9),
]


def peaking_sos(f0, gain_db, q, sr):
    b, a = iirpeak(f0 / (sr / 2.0), q)
    sos = tf2sos(b, a)
    # iirpeak is 0 dB at DC and +? at centre; scale to requested gain
    lin = 10 ** (gain_db / 20.0) - 1.0
    sos[0, :3] = sos[0, :3] * (1.0 + lin) if False else sos[0, :3]
    return sos, lin


def apply_peaking(x, f0, gain_db, q, sr):
    """RBJ peaking EQ, applied zero-phase.

    sosfiltfilt runs the filter forwards then backwards, so the magnitude
    response is |H|^2 — the naive gain would be doubled in dB. Halving the
    dB gain here makes the requested value the value you actually get.
    """
    A = 10 ** (gain_db / 80.0)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    b = np.array([1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A])
    a = np.array([1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A])
    return sosfiltfilt(tf2sos(b, a), x)


def main():
    src, out = sys.argv[1], sys.argv[2]
    curve = DEFAULT_CURVE
    if len(sys.argv) > 3 and sys.argv[3] != "-":
        curve = []
        for part in sys.argv[3].split(","):
            f, g, q = part.split(":")
            curve.append((float(f), float(g), float(q)))

    y, sr = sf.read(src, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    peak0 = np.max(np.abs(y)) + 1e-9

    for f0, g, q in curve:
        y = apply_peaking(y, f0, g, q, sr)
        print(f"  {f0:7.0f} Hz  {g:+.1f} dB  Q={q}")

    y = y / (np.max(np.abs(y)) + 1e-9) * peak0
    sf.write(out, y.astype("float32"), sr)
    print(f"wrote {out}  sr={sr} dur={len(y) / sr:.2f}s peak={np.max(np.abs(y)):.3f}")


if __name__ == "__main__":
    main()
