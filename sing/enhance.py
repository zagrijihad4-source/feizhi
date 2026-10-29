"""Repair the three defects the trained model cannot fix on its own.

1. articulation  - transient shaping: emphasise each syllable's attack so
                   consonants land harder
2. capture       - a noise gate tames the residual noise floor lifted from
                   the separated training material
3. capture/air   - a harmonic exciter synthesises 7-14 kHz content from the
                   2-6 kHz band, because the Douyin source tops out low and no
                   amount of training can recreate what was never there
Plus a 85 Hz high-pass to strip the bass/kick residue measured at 7.3%.

usage: python enhance.py <in.wav> <out.wav> [air_db] [attack] [gate]
"""
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt, hilbert


def hp(x, sr, f=85.0, order=4):
    return sosfiltfilt(butter(order, f / (sr / 2), btype="highpass", output="sos"), x)


def bandpass(x, sr, lo, hi, order=4):
    return sosfiltfilt(butter(order, [lo / (sr / 2), hi / (sr / 2)], btype="band", output="sos"), x)


def exciter(x, sr, air_db=6.0, lo=2000.0, hi_band=(7000.0, 14000.0)):
    """Generate upper harmonics from a low band and mix them into a high band.

    lo/hi_band default to the 8-14 kHz "air" region, but WeChat voice clips are
    16 kHz mono SILK, so anything above 8 kHz is destroyed in transit. Pass
    lo=1500, hi_band=(3000, 6000) to place the effect inside what WeChat keeps.
    """
    src = bandpass(x, sr, lo, lo + 4000)
    driven = np.tanh(src * 6.0)                      # nonlinearity -> harmonics
    hi = bandpass(driven, sr, hi_band[0], hi_band[1])
    # match the level of the generated band to the requested lift
    ref = np.sqrt(np.mean(src ** 2)) + 1e-12
    cur = np.sqrt(np.mean(hi ** 2)) + 1e-12
    target = ref * (10 ** (air_db / 20.0)) * 0.5
    return x + hi * (target / cur)


def transient(x, sr, amount=0.35, win_ms=8.0):
    """Boost frame onsets: raise gain where the envelope is rising."""
    w = max(1, int(sr * win_ms / 1000.0))
    env = np.abs(hilbert(x))
    k = np.ones(w) / w
    sm = np.convolve(env, k, mode="same")
    d = np.gradient(sm)
    gain = 1.0 + amount * np.tanh(d / (np.max(np.abs(d)) + 1e-12) * 3.0)
    return x * gain


def gate(x, sr, thresh_db=-38.0, ratio=0.35):
    """Gentle downward expansion below the threshold, frame-wise."""
    w = max(1, int(sr * 0.010))
    env = np.abs(hilbert(x))
    k = np.ones(w) / w
    sm = np.convolve(env, k, mode="same")
    db = 20 * np.log10(sm + 1e-9)
    thr = np.max(db) + thresh_db
    g = np.ones_like(db)
    below = db < thr
    g[below] = 1.0 - (1.0 - ratio) * np.clip((thr - db[below]) / 25.0, 0, 1)
    return x * g


def main():
    src_p, dst_p = sys.argv[1], sys.argv[2]
    air_db = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
    attack = float(sys.argv[4]) if len(sys.argv) > 4 else 0.35
    use_gate = (sys.argv[5] if len(sys.argv) > 5 else "1") not in ("0", "no", "false")
    mode = sys.argv[6] if len(sys.argv) > 6 else "air"

    y, sr = sf.read(src_p, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    peak0 = np.max(np.abs(y)) + 1e-9

    y = hp(y, sr)
    if mode == "wx":
        # everything must live inside the 0-8 kHz band WeChat actually carries
        y = exciter(y, sr, air_db=air_db, lo=1500.0, hi_band=(3000.0, 6000.0))
    else:
        y = exciter(y, sr, air_db=air_db)
    y = transient(y, sr, amount=attack)
    if use_gate:
        y = gate(y, sr)
    y = y / (np.max(np.abs(y)) + 1e-9) * peak0 * 0.98
    sf.write(dst_p, y.astype("float32"), sr)
    print("mode=%s air +%.1f dB attack %.2f gate %s -> %s"
          % (mode, air_db, attack, use_gate, dst_p))


if __name__ == "__main__":
    main()
