"""Mix a converted vocal with the instrumental and emit delivery artefacts.

Sample-rate agnostic: the RVC model runs at 40 kHz, SoulX at 24 kHz, the
instrumental is 44.1 kHz. Everything is resampled to 44.1 kHz for the mix, and
WeChat voice slices are produced as 16 kHz mono s16le with polyphase
resampling so there is no aliasing.

usage: python mix_and_slice.py <vocal.wav> <out_dir> <gain> [slice_sec]
"""
import glob
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(HERE, "source", "taoxi_inst.wav")
SR = 44100


def load_mono(path, sr=SR):
    y, s = sf.read(path, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if s != sr:
        from math import gcd

        g = gcd(int(s), int(sr))
        y = resample_poly(y, sr // g, s // g)
    return y


def dyn_db(x, sr=SR, hop=882):
    r = librosa.feature.rms(y=x.astype("float32"), hop_length=hop)[0]
    db = 20 * np.log10(r + 1e-9)
    on = db > np.max(db) - 45
    d = db[on]
    return float(np.percentile(d, 5)), float(np.percentile(d, 95))


def main():
    vocal_p, out_dir = sys.argv[1], sys.argv[2]
    gain = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
    slice_sec = float(sys.argv[4]) if len(sys.argv) > 4 else 42.0

    os.makedirs(out_dir, exist_ok=True)
    voc = load_mono(vocal_p)
    inst = load_mono(INST)
    n = min(len(voc), len(inst))
    voc, inst = voc[:n], inst[:n]
    print("vocal %.2fs  inst %.2fs  sr=%d" % (n / SR, len(inst) / SR, SR))

    a = voc / (np.sqrt(np.mean(voc ** 2)) + 1e-9)
    b = inst / (np.sqrt(np.mean(inst ** 2)) + 1e-9)

    dry = a / (np.max(np.abs(a)) + 1e-9) * 0.89
    p5, p95 = dyn_db(dry)
    print("dry vocal dynamic  %.1f dB  (p5 %.1f .. p95 %.1f)" % (p95 - p5, p5, p95))

    mix = a + gain * b
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.89
    p5m, p95m = dyn_db(mix)
    print("mix (inst %.2f)   dynamic  %.1f dB" % (gain, p95m - p5m))

    wav = os.path.join(out_dir, "mix.wav")
    dryp = os.path.join(out_dir, "dry.wav")
    sf.write(wav, mix.astype("float32"), SR)
    sf.write(dryp, dry.astype("float32"), SR)
    print("wrote", wav)
    print("wrote", dryp)

    pcm_dir = os.path.join(out_dir, "pcm")
    os.makedirs(pcm_dir, exist_ok=True)
    for f in glob.glob(os.path.join(pcm_dir, "*.pcm")):
        os.remove(f)
    step = int(slice_sec * SR)
    i = 0
    for s in range(0, n, step):
        seg = mix[s:s + step]
        if len(seg) < SR * 3:
            break
        pcm = resample_poly(seg, 16000, SR)
        np.clip(pcm * 32767, -32768, 32767).astype("<i2").tofile(
            os.path.join(pcm_dir, "slice%d.pcm" % i)
        )
        i += 1
    print("pcm slices:", i, "x %.0fs" % slice_sec)


if __name__ == "__main__":
    main()
