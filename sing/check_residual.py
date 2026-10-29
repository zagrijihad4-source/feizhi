"""Measure accompaniment leakage in the training material.

A singer's fundamental sits at 232-438 Hz for this corpus, so real vocal energy
belongs in 250-2000 Hz. Anything substantial at 40-120 Hz is bass/kick residue
from imperfect separation, and 4-12 kHz excess is separation hiss.
"""
import glob
import os

import librosa
import numpy as np

BANDS = [(40, 120), (120, 250), (250, 500), (500, 1000),
         (1000, 2000), (2000, 4000), (4000, 8000), (8000, 12000)]


def main():
    files = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "source", "dy_top", "*.wav")))
    head = "%-26s " % "file" + " ".join(("%d-%d" % b).rjust(10) for b in BANDS)
    print(head)
    tot = np.zeros(len(BANDS))
    rows = []
    for f in files:
        y, sr = librosa.load(f, sr=24000, mono=True)
        S = np.abs(librosa.stft(y.astype("float32"), n_fft=2048, hop_length=512)) ** 2
        fr = librosa.fft_frequencies(sr=24000, n_fft=2048)
        v = np.array([S[(fr >= lo) & (fr < hi)].sum() for lo, hi in BANDS])
        v = v / v.sum()
        tot += v
        rows.append((os.path.basename(f), v))
        if len(rows) <= 12:
            print("%-26s " % os.path.basename(f)[:26] + " ".join("%9.2f%%" % (x * 100) for x in v))
    m = tot / len(rows)
    print("-" * len(head))
    print("%-26s " % ("MEAN (%d clips)" % len(rows)) + " ".join("%9.2f%%" % (x * 100) for x in m))
    lo = m[0] + m[1]
    print()
    print("40-250 Hz (bass/kick residue) : %.2f%%" % (lo * 100))
    print("250-2000 Hz (vocal body)      : %.2f%%" % ((m[2] + m[3] + m[4]) * 100))
    print("4-12 kHz (separation hiss)    : %.2f%%" % ((m[6] + m[7]) * 100))
    v = sorted((r[1], r[0]) for r in rows[::-1])
    worst = max(rows, key=lambda r: r[1][0] + r[1][1])
    print("worst low-end clip            : %s  %.2f%%" % (worst[0], (worst[1][0] + worst[1][1]) * 100))


if __name__ == "__main__":
    main()
