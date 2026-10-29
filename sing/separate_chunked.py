"""Separate long recordings by explicit 10 s windows.

VocalSeparator.process() stalls on ~22 s inputs here even though 10 s works in
5.8 s, and its own internal chunking is what misbehaves. Driving the windowing
ourselves keeps every forward pass in the range that is known to work.

usage: python separate_chunked.py [src_dir] [out_dir]
"""
import sys
import time
from math import gcd
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
sys.path.insert(0, str(SING / "SoulX-Singer"))

import numpy as np
import soundfile as sf
from scipy import signal as sps

from preprocess.tools.vocal_separation.model import VocalSeparator

ROOT = SING / "pretrained_models" / "SoulX-Singer-Preprocess"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else SING / "source" / "batch_mono"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SING / "source" / "clean_vocals"
TMP = SING / "source" / "_chunk_tmp"
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)

SR = 44100
WIN = 10.0
OVERLAP = 1.0


def resample(x, a, b):
    if a == b:
        return x.astype(np.float32)
    g = gcd(int(a), int(b))
    return sps.resample_poly(x, b // g, a // g).astype(np.float32)


def main():
    files = sorted(SRC.glob("*.wav"))
    print("sources: %d  window %.1fs overlap %.1fs" % (len(files), WIN, OVERLAP), flush=True)

    t0 = time.time()
    sep = VocalSeparator(
        sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
        sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
        der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
        der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
        device="cuda",
        use_der=False,
        verbose=False,
        chunk_length_sec=5,
    )
    print("model loaded %.1fs" % (time.time() - t0), flush=True)

    hop = int((WIN - OVERLAP) * SR)
    win_n = int(WIN * SR)
    tmp_in = TMP / "in.wav"

    for fi, f in enumerate(files, 1):
        dst = OUT / f.name
        if dst.exists() and dst.stat().st_size > 10000:
            print("  [%2d/%d] %-12s skip" % (fi, len(files), f.name), flush=True)
            continue

        x, sr = sf.read(str(f), dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if sr != SR:
            x = resample(x, sr, SR)

        pieces = []
        ipieces = []
        starts = list(range(0, max(len(x) - 1, 1), hop))
        for si, s in enumerate(starts):
            seg = x[s:s + win_n]
            if len(seg) < int(0.5 * SR):
                continue
            sf.write(str(tmp_in), seg, SR, subtype="PCM_16")
            try:
                out = sep.process(str(tmp_in))
            except Exception as exc:  # noqa: BLE001
                print("      chunk %d failed: %s" % (si, exc), flush=True)
                pieces.append((s, seg.copy()))     # fall back to the raw audio
                ipieces.append((s, np.zeros(len(seg), dtype=np.float32)))
                continue
            voc = np.asarray(out.vocals)
            if voc.ndim > 1:
                voc = voc.mean(axis=0) if voc.shape[0] < voc.shape[-1] else voc.mean(axis=-1)
            voc = resample(voc.astype(np.float32), int(out.sample_rate), SR)
            if len(voc) < len(seg):
                voc = np.pad(voc, (0, len(seg) - len(voc)))
            pieces.append((s, voc[:len(seg)]))

            acc = np.asarray(out.accompaniment)
            if acc.ndim > 1:
                acc = acc.mean(axis=0) if acc.shape[0] < acc.shape[-1] else acc.mean(axis=-1)
            acc = resample(acc.astype(np.float32), int(out.sample_rate), SR)
            if len(acc) < len(seg):
                acc = np.pad(acc, (0, len(seg) - len(acc)))
            ipieces.append((s, acc[:len(seg)]))

        # overlap-add with a linear cross-fade
        total = np.zeros(len(x), dtype=np.float32)
        weight = np.zeros(len(x), dtype=np.float32)
        fade_n = int(OVERLAP * SR)
        for s, seg in pieces:
            n = len(seg)
            w = np.ones(n, dtype=np.float32)
            if fade_n > 0 and n > 2 * fade_n:
                ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
                w[:fade_n] = ramp
                w[-fade_n:] = ramp[::-1]
            total[s:s + n] += seg * w
            weight[s:s + n] += w
        weight[weight < 1e-6] = 1.0
        y = total / weight

        peak = float(np.abs(y).max())
        if peak > 0.99:
            y = y / peak * 0.99
        sf.write(str(dst), y, SR, subtype="PCM_16")

        itotal = np.zeros(len(x), dtype=np.float32)
        iw = np.zeros(len(x), dtype=np.float32)
        for s, aseg in ipieces:
            n = len(aseg)
            w = np.ones(n, dtype=np.float32)
            if fade_n > 0 and n > 2 * fade_n:
                ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
                w[:fade_n] = ramp
                w[-fade_n:] = ramp[::-1]
            itotal[s:s + n] += aseg * w
            iw[s:s + n] += w
        iw[iw < 1e-6] = 1.0
        inst = itotal / iw
        ipk = float(np.abs(inst).max())
        if ipk > 0.99:
            inst = inst / ipk * 0.99
        (OUT / "inst").mkdir(parents=True, exist_ok=True)
        sf.write(str(OUT / "inst" / f.name), inst, SR, subtype="PCM_16")
        print("      also wrote accompaniment:", OUT / "inst" / f.name, flush=True)
        print("  [%2d/%d] %-12s %5.1fs  %d chunks  peak %.3f  %.0fs elapsed"
              % (fi, len(files), f.name, len(y) / SR, len(pieces), peak, time.time() - t0), flush=True)

    print("\ndone %.1fs -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
