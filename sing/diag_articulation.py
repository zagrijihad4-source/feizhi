"""Objective proxies for the three complaints: articulation, expression, capture.

Articulation  -> consonant band energy (4-8 kHz) and spectral flatness
                 (fricatives are noise-like: high flatness; vowels are harmonic)
Expression    -> short-time energy modulation depth and F0 movement
Capture       -> noise floor in silent frames, plus unnatural HF hiss
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def analyse(path, label):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    fr = librosa.fft_frequencies(sr=sr, n_fft=1024)
    P = S ** 2
    tot = P.sum() + 1e-12

    def band(lo, hi):
        return float(P[(fr >= lo) & (fr < hi)].sum() / tot)

    cent = float(np.median(librosa.feature.spectral_centroid(S=S, sr=sr)[0]))
    flat = float(np.median(librosa.feature.spectral_flatness(S=S)[0]))

    r = librosa.feature.rms(y=y, hop_length=256)[0]
    db = 20 * np.log10(r + 1e-9)
    on = db > np.max(db) - 45
    d = db[on]
    dyn = float(np.percentile(d, 95) - np.percentile(d, 5))
    # modulation: how much loudness moves between adjacent 32 ms frames
    d1 = np.abs(np.diff(d))
    mod = float(np.median(d1))

    # noise floor: quietest 5% of frames that still contain signal
    floor = float(np.mean(np.sort(d)[: max(1, len(d) // 20)]))

    f0 = librosa.yin(y, fmin=70, fmax=900, sr=sr, hop_length=256)
    v = f0[f0 > 0]
    st = 12 * np.log2(v / 440.0) if len(v) > 50 else np.array([0.0])
    f0sd = float(np.std(st))
    micro = float(np.std(st - np.convolve(st, np.ones(9) / 9, mode="same")))

    print("%-20s cent=%5.0f  4-8k=%5.2f%%  flat=%.4f  dyn=%5.1f  mod=%4.2f  "
          "floor=%6.1f  f0sd=%4.2f  vib=%4.3f  8-12k=%5.2f%%"
          % (label, cent, band(4000, 8000) * 100, flat, dyn, mod, floor, f0sd, micro,
             band(8000, 12000) * 100))


def main():
    print("%-20s %5s  %7s  %8s  %5s  %4s  %6s  %5s  %5s  %6s"
          % ("", "cent", "4-8k", "flat", "dyn", "mod", "floor", "f0sd", "vib", "8-12k"))
    items = [
        ("source/taoxi_vocal.wav", "SRC 源唱段"),
        ("outputs/rvc/_y6clean45.wav", "RVC y6 (旧)"),
        ("outputs/soulx/t45_pY1.wav", "SoulX 抖音参考"),
        ("outputs/rvc/t45_p033.wav", "y9 protect .33"),
        ("outputs/rvc/t45_p07.wav", "y9 protect .70"),
        ("outputs/rvc/t45_p09.wav", "y9 protect .90"),
    ]
    for rel, label in items:
        p = os.path.join(HERE, rel)
        if not os.path.exists(p):
            print("%-20s (missing)" % label)
            continue
        analyse(p, label)
    # protect 0.5 version is the full-song output; crop the same window
    full = os.path.join(HERE, "outputs", "rvc", "taoxi_y9.wav")
    if os.path.exists(full):
        y, sr = sf.read(full, dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        tmp = os.path.join(HERE, "outputs", "rvc", "_t45_p05.wav")
        sf.write(tmp, y[: int(45 * sr)], sr)
        analyse(tmp, "y9 protect .50")


if __name__ == "__main__":
    main()
