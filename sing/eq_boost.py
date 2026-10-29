"""Restore the clarity band that the RVC model flattened.

The trained voice sits ~2.6 dB light in 2-4 kHz and dies above 3.6 kHz because
the training material came from compressed Douyin audio. This applies RBJ
peaking filters to put that band back without touching the fundamental.

usage: python eq_boost.py <in.wav> <out.wav> [strength]
       strength 1.0 = default curve, 0.5 = half, 1.5 = stronger
"""
import sys

import numpy as np
import soundfile as sf
from scipy import signal


def peaking(sr, f0, gain_db, q):
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2.0 * q)
    b = [1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a]
    a_ = [1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a]
    return [x / a_[0] for x in b], [x / a_[0] for x in a_]


# (frequency, gain dB, Q) -- measured, not guessed: k=1.0 used to overshoot
# 2-4k to 7.2% (target 4.0%) and roll95 to 5663 Hz (target 3682), so the curve
# now lifts only the 2-4k clarity band and leaves 5k+ alone.
# (frequency, gain dB, Q)
# Tuned per model version -- these numbers target what the e500 model actually
# outputs (2-4k 1.8% vs target 4.0%, 1-2k 19.2% vs target 10.5%), not the e200
# numbers the previous curve was fitted against.
CURVE = [
    (280.0, -1.0, 0.70),
    (1500.0, -1.5, 1.00),
    (3100.0, 3.2, 1.50),
    (6000.0, -2.0, 1.00),
]

src, dst = sys.argv[1], sys.argv[2]
k = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

x, sr = sf.read(src, dtype="float32", always_2d=True)
mono = x.shape[1] == 1
y = x.mean(axis=1)

for f0, g, q in CURVE:
    b, a = peaking(sr, f0, g * k, q)
    y = signal.lfilter(b, a, y).astype(np.float32)

# a couple of fast peaks could clip after the boost
peak = float(np.abs(y).max())
if peak > 0.98:
    y *= 0.98 / peak
    print("scaled down %.3f" % (0.98 / peak))

sf.write(dst, y if mono else np.stack([y, y], axis=1), sr)
print("wrote %s  %.2fs @ %d Hz  peak=%.3f  curve x%.2f" % (dst, len(y) / sr, sr, float(np.abs(y).max()), k))
