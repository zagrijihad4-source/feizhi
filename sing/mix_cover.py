"""Mix a converted vocal back onto its instrumental.

usage: python mix_cover.py <cover.wav> <inst.wav> <out.wav> [vocal_gain] [inst_gain]
"""
import sys

import numpy as np
import soundfile as sf


def read(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    return x.mean(axis=1), sr


def resample(x, a, b):
    if a == b:
        return x
    n = int(round(len(x) * b / a))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


cover_path, inst_path, out_path = sys.argv[1:4]
vg = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
ig = float(sys.argv[5]) if len(sys.argv) > 5 else 0.8

voc, vsr = read(cover_path)
inst, isr = read(inst_path)
sr = isr
voc = resample(voc, vsr, sr)

n = max(len(voc), len(inst))
mix = np.zeros(n, dtype=np.float32)
mix[: len(voc)] += voc * vg
mix[: len(inst)] += inst * ig

peak = float(np.abs(mix).max())
print("vocal %.2fs  inst %.2fs  mix %.2fs  pre-peak %.3f" % (len(voc) / sr, len(inst) / sr, n / sr, peak))
if peak > 0.98:
    mix *= 0.98 / peak
    print("normalised to 0.98 (gain %.3f)" % (0.98 / peak))

sf.write(out_path, mix, sr)
print("wrote %s @ %d Hz  peak=%.3f" % (out_path, sr, float(np.abs(mix).max())))
