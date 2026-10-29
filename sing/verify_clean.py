"""Verify that separation actually produced clean vocals before spending hours training.

Three independent checks, because no single metric catches every kind of dirt:

  1  二次分离   run the separator AGAIN on the "clean" output; whatever it still
                calls accompaniment is residual bleed. Energy ratio ~0 means clean.
  2  静音残留   at places where the vocal itself is silent, a clean track should be
                near-silent. A constant floor there is accompaniment or hiss.
  3  频谱形状   roll95 far above the natural range means separation artifacts are
                dominating rather than voice.

usage: python verify_clean.py [clean_dir] [sample_n]
"""
import random
import sys
import time
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
sys.path.insert(0, str(SING / "SoulX-Singer"))

import numpy as np
import soundfile as sf

from preprocess.tools.vocal_separation.model import VocalSeparator

ROOT = SING / "pretrained_models" / "SoulX-Singer-Preprocess"
CLEAN = Path(sys.argv[1]) if len(sys.argv) > 1 else SING / "source" / "dy_clean"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
TMP = SING / "source" / "_verify_tmp"
TMP.mkdir(parents=True, exist_ok=True)

SR = 44100


def roll95(x, sr):
    win = 4096
    acc = np.zeros(win // 2 + 1)
    c = 0
    for i in range(0, len(x) - win, win // 2):
        acc += np.abs(np.fft.rfft(x[i:i + win] * np.hanning(win))) ** 2
        c += 1
    if c == 0:
        return None
    f = np.fft.rfftfreq(win, 1 / sr)
    tot = acc.sum()
    return float(f[np.searchsorted(np.cumsum(acc) / tot, 0.95)]) if tot > 0 else None


def floor_ratio(x, sr):
    """energy in the quietest 20% of 20ms windows, relative to the loud ones"""
    w = int(0.02 * sr)
    n = len(x) // w
    if n < 10:
        return None
    rms = np.array([np.sqrt(np.mean(x[i * w:(i + 1) * w] ** 2)) for i in range(n)])
    thr = np.percentile(rms, 20)
    quiet = rms[rms <= thr].mean()
    loud = rms[rms > np.percentile(rms, 60)].mean()
    return float(quiet / max(loud, 1e-9))


def main():
    files = sorted(CLEAN.glob("*.wav"))
    if not files:
        print("no files in %s" % CLEAN)
        return 1
    random.seed(42)
    sample = files if len(files) <= N else random.sample(files, N)
    print("clean dir: %s   total %d   sampling %d\n" % (CLEAN, len(files), len(sample)), flush=True)

    t0 = time.time()
    sep = VocalSeparator(
        sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
        sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
        der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
        der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
        device="cuda", use_der=False, verbose=False, chunk_length_sec=5,
    )
    print("separator loaded %.1fs\n" % (time.time() - t0), flush=True)

    print("%-22s %8s %8s %9s %9s %7s" % ("file", "dur", "r95", "floor", "2nd-inst", "verdict"))
    rows = []
    tmp_in = TMP / "in.wav"
    for f in sample:
        x, sr = sf.read(str(f), dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if sr != SR:
            from math import gcd
            from scipy import signal as sps
            g = gcd(int(sr), SR)
            x = sps.resample_poly(x, SR // g, sr // g).astype(np.float32)
        r95 = roll95(x, sr if sr == SR else SR)
        fl = floor_ratio(x, SR)

        # second pass: whatever it calls accompaniment now is residual bleed
        seg = x[: int(8 * SR)]
        sf.write(str(tmp_in), seg, SR, subtype="PCM_16")
        try:
            out = sep.process(str(tmp_in))
            v2 = np.asarray(out.vocals)
            i2 = np.asarray(out.accompaniment)
            if v2.ndim > 1:
                v2 = v2.mean(axis=0) if v2.shape[0] < v2.shape[-1] else v2.mean(axis=-1)
            if i2.ndim > 1:
                i2 = i2.mean(axis=0) if i2.shape[0] < i2.shape[-1] else i2.mean(axis=-1)
            bleed = float(np.sqrt(np.mean(i2 ** 2)) / max(np.sqrt(np.mean(v2 ** 2)), 1e-9))
        except Exception as exc:  # noqa: BLE001
            bleed = float("nan")

        bad = []
        if fl is not None and fl > 0.15:
            bad.append("floor高")
        if bleed == bleed and bleed > 0.6:
            bad.append("残留伴奏")
        if r95 is not None and (r95 > 6500 or r95 < 2000):
            bad.append("频谱异常")
        verdict = "OK" if not bad else ",".join(bad)
        rows.append((f.name, len(x) / SR, r95, fl, bleed, verdict))
        print("%-22s %7.1fs %8.0f %9.3f %9.2f %7s" % (f.name[:22], len(x) / SR, r95 or 0, fl or 0, bleed, verdict), flush=True)

    ok = sum(1 for r in rows if r[5] == "OK")
    floors = [r[3] for r in rows if r[3] is not None]
    bleeds = [r[4] for r in rows if r[4] == r[4]]
    print("\n=== summary ===")
    print("OK %d / %d" % (ok, len(rows)))
    if floors:
        print("floor ratio   mean %.3f  max %.3f   (clean < 0.15)" % (np.mean(floors), max(floors)))
    if bleeds:
        print("2nd-pass bleed mean %.2f  max %.2f   (clean < 0.60)" % (np.mean(bleeds), max(bleeds)))
    print("elapsed %.0fs" % (time.time() - t0))
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    sys.exit(main())
