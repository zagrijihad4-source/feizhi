"""Identity check: is each converted file actually different from the source,
and are the different model versions different from each other?

If the RVC path silently passed the source through, every row will correlate
with taoxi_vocal at ~0.99.
"""
import sys

import numpy as np
import soundfile as sf

SR = 16000


def load(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def mel_spec(x, n_fft=1024, hop=256, n_mels=64):
    win = np.hanning(n_fft).astype(np.float32)
    frames = []
    for i in range(0, len(x) - n_fft, hop):
        frames.append(np.abs(np.fft.rfft(x[i:i + n_fft] * win)) ** 2)
    if not frames:
        return None
    S = np.array(frames).T
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    # simple triangular mel filterbank
    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700.0)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595.0) - 1)

    mels = np.linspace(hz2mel(0), hz2mel(SR / 2), n_mels + 2)
    hz = mel2hz(mels)
    fb = np.zeros((n_mels, len(freqs)))
    for m in range(n_mels):
        lo, ce, hi = hz[m], hz[m + 1], hz[m + 2]
        for k, f in enumerate(freqs):
            if lo <= f <= ce:
                fb[m, k] = (f - lo) / max(ce - lo, 1e-9)
            elif ce < f <= hi:
                fb[m, k] = (hi - f) / max(hi - ce, 1e-9)
    return np.log(fb @ S + 1e-10)


def cos(a, b):
    n = min(a.shape[1], b.shape[1])
    a = a[:, :n]
    b = b[:, :n]
    # compare per-frame, then average (framewise timbre similarity)
    num = (a * b).sum(axis=0)
    den = np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9
    return float(np.mean(num / den))


def wave_corr(a, b):
    n = min(len(a), len(b))
    a = a[:n] - a[:n].mean()
    b = b[:n] - b[:n].mean()
    return float(np.corrcoef(a, b)[0, 1])


paths = sys.argv[1:]
names = [p.split("\\")[-1].replace(".wav", "") for p in paths]
sig = {}
spec = {}
for p, nm in zip(paths, names):
    x = load(p)
    sig[nm] = x
    spec[nm] = mel_spec(x)

print("=== waveform correlation (resampling alone would give ~0.99) ===")
print("%-18s" % "", "".join("%-12s" % n[:11] for n in names))
for a in names:
    row = "%-18s" % a[:17]
    for b in names:
        row += "%-12.4f" % wave_corr(sig[a], sig[b])
    print(row)

print()
print("=== per-frame mel-spectrogram cosine (timbre identity) ===")
print("%-18s" % "", "".join("%-12s" % n[:11] for n in names))
for a in names:
    row = "%-18s" % a[:17]
    for b in names:
        row += "%-12.4f" % cos(spec[a], spec[b])
    print(row)
