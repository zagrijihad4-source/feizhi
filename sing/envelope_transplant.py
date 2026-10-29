"""Envelope transplant: give the converted vocal the source performance's
loudness dynamics without touching timbre.

The singer's own recordings sit at ~9.5 dB of dynamic range (flat, close-mic
delivery), while the reference song spans ~34 dB. A converter faithfully
reproduces the flat delivery, which reads as "no emotion". Here the converted
audio keeps its timbre and gains the source stem's per-frame loudness contour.

usage: python envelope_transplant.py <converted.wav> <source.wav> <out.wav> [strength]
"""
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d

HOP = 480
SR = 24000


def envelope(path, sr=SR, hop=HOP, smooth_ms=60):
    y, _ = librosa.load(path, sr=sr, mono=True)
    r = librosa.feature.rms(y=y.astype("float32"), hop_length=hop, frame_length=1024)[0]
    db = 20 * np.log10(r + 1e-9)
    sigma = max(1.0, smooth_ms / (hop / sr * 1000))
    return db, gaussian_filter1d(db, sigma), y


def main():
    conv_p, src_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    strength = float(sys.argv[4]) if len(sys.argv) > 4 else 0.85
    max_gain = float(sys.argv[5]) if len(sys.argv) > 5 else 16.0
    smooth_ms = float(sys.argv[6]) if len(sys.argv) > 6 else 60.0

    db_c, sm_c, y = envelope(conv_p, smooth_ms=smooth_ms)
    db_s, sm_s, _ = envelope(src_p, smooth_ms=smooth_ms)

    n = min(len(sm_c), len(sm_s))
    sm_c, sm_s, db_c = sm_c[:n], sm_s[:n], db_c[:n]

    # gate: only reshape where the source actually has signal
    floor = np.max(sm_s) - 42.0
    active = sm_s > floor

    gain_db = (sm_s - sm_c) * strength
    gain_db = np.clip(gain_db, -max_gain, max_gain)
    gain_db = gaussian_filter1d(gain_db, 2.0)

    # smooth crossfade at the gate edges so gated gaps do not pop
    ramp = gaussian_filter1d(active.astype("float64"), 4.0)
    gain_db = gain_db * ramp

    frames = np.arange(len(y)) / HOP
    gain_lin = np.interp(frames, np.arange(n), np.power(10.0, gain_db / 20.0))
    y2 = y * gain_lin
    peak = np.max(np.abs(y2))
    if peak > 0:
        y2 = y2 / peak * 0.95

    sf.write(out_p, y2.astype("float32"), SR)

    r2 = librosa.feature.rms(y=y2.astype("float32"), hop_length=HOP)[0]
    d2 = 20 * np.log10(r2 + 1e-9)
    on = d2 > np.max(d2) - 45
    before = np.percentile(db_c[db_c > np.max(db_c) - 45], 95) - np.percentile(db_c[db_c > np.max(db_c) - 45], 5)
    after = d2[on]
    print(f"strength={strength} max_gain={max_gain} dB")
    print(f"range before={before:.1f} dB  after={after.max() - after.min():.1f} dB "
          f"(p5..p95 {np.percentile(after, 5):.1f}..{np.percentile(after, 95):.1f})")
    print(f"gain applied: mean={gain_db[active].mean():+.2f} dB  "
          f"p5={np.percentile(gain_db[active], 5):+.2f}  p95={np.percentile(gain_db[active], 95):+.2f}")
    print("wrote", out_p)


if __name__ == "__main__":
    main()
