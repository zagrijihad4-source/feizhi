"""Build an A/B pair from the same 42 s window so the dynamic change is audible.

A = raw SoulX output, B = envelope-transplanted. Both rendered dry (no
instrumental) because the backing track's constant loudness masks the very
change we want to demonstrate.
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs", "soulx", "ab")
START = 120.0
DUR = 42.0
SR = 24000


def grab(path):
    y, s = sf.read(path, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    i0 = int(START * s)
    i1 = int((START + DUR) * s)
    seg = y[i0:i1]
    seg = seg / (np.max(np.abs(seg)) + 1e-9) * 0.9
    return resample_poly(seg, 16000, int(s))


def main():
    os.makedirs(OUT, exist_ok=True)
    for tag, src in [
        ("A_raw", "outputs/soulx/taoxi_full_soulx.wav"),
        ("B_dyn", "outputs/soulx/taoxi_full_dyn.wav"),
    ]:
        pcm = grab(os.path.join(HERE, src))
        p = os.path.join(OUT, f"{tag}.pcm")
        np.clip(pcm * 32767, -32768, 32767).astype("<i2").tofile(p)
        print(f"{tag}: {len(pcm) / 16000:.1f}s -> {p}")


if __name__ == "__main__":
    main()
