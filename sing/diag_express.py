"""Diagnose expressiveness loss: compare F0 contour and loudness dynamics
between the source vocal and the SoulX output.
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
SX = os.path.join(HERE, "SoulX-Singer")
sys.path.insert(0, SX)
from preprocess.tools.f0_extraction import F0Extractor  # noqa: E402


def f0_of(ex, path, sr=24000):
    f0 = ex.process(path, verbose=False)
    return np.asarray(f0, dtype=np.float64)


def rms_db(path, sr=24000):
    y, _ = librosa.load(path, sr=sr, mono=True)
    r = librosa.feature.rms(y=y.astype("float32"), hop_length=480)[0]
    db = 20 * np.log10(r + 1e-9)
    voiced = db > (np.max(db) - 45)
    return db, voiced


def contour_stats(name, f0, db, voiced):
    v = (f0 > 0) & voiced[:len(f0)]
    if v.sum() < 50:
        print(f"{name}: too few voiced frames")
        return
    st = 12 * np.log2(f0[v] / 440.0)
    print(f"{name}")
    print(f"   frames={len(f0)} voiced={v.mean():.3f}")
    print(f"   pitch semitone: mean={st.mean():7.2f} std={st.std():5.2f} "
          f"p5={np.percentile(st, 5):7.2f} p95={np.percentile(st, 95):7.2f} "
          f"range={np.percentile(st, 95) - np.percentile(st, 5):5.2f}")
    # contour motion: frame-to-frame and 0.5 s swing
    d1 = np.abs(np.diff(st))
    win = 25  # 0.5 s at hop 480 / 24 kHz
    if len(st) > win:
        swing = np.abs(np.convolve(st, np.ones(win) / win, mode="valid"))
        print(f"   |dPitch| per frame: mean={d1.mean():.3f} p95={np.percentile(d1, 95):.3f}")
    dv = db[voiced]
    print(f"   loudness dB: p5={np.percentile(dv, 5):6.1f} p95={np.percentile(dv, 95):6.1f} "
          f"range={np.percentile(dv, 95) - np.percentile(dv, 5):5.1f}")


def main():
    ex = F0Extractor(
        os.path.join(HERE, "pretrained_models/SoulX-Singer-Preprocess/rmvpe/rmvpe.pt"),
        device="cuda",
        target_sr=24000,
        hop_size=480,
        verbose=False,
    )
    src = os.path.join(HERE, "source", "taoxi_vocal.wav")
    out = os.path.join(HERE, "outputs", "soulx", "taoxi_full_soulx.wav")

    f0_src = f0_of(ex, src)
    f0_out = f0_of(ex, out)
    db_src, v_src = rms_db(src)
    db_out, v_out = rms_db(out)

    print(f"src frames={len(f0_src)} out frames={len(f0_out)}")
    contour_stats("SOURCE taoxi_vocal", f0_src, db_src, v_src)
    contour_stats("OUTPUT soulx", f0_out, db_out, v_out)

    n = min(len(f0_src), len(f0_out))
    a, b = f0_src[:n], f0_out[:n]
    both = (a > 0) & (b > 0)
    if both.sum() > 100:
        sa = 12 * np.log2(a[both] / 440.0)
        sb = 12 * np.log2(b[both] / 440.0)
        diff = sb - sa
        corr = float(np.corrcoef(sa, sb)[0, 1])
        print("\nPITCH TRANSFER (voiced overlap)")
        print(f"   frames={both.sum()} corr={corr:.4f}")
        print(f"   offset median={np.median(diff):+.2f} st  "
              f"residual std={diff.std():.2f} st  "
              f"residual p95|.|={np.percentile(np.abs(diff), 95):.2f} st")
        # vibrato / micro-motion survival: high-frequency part of the contour
        k = 9
        ker = np.ones(k) / k
        ma = np.convolve(sa, ker, mode="same")
        mb = np.convolve(sb, ker, mode="same")
        va, vb = sa - ma, sb - mb
        print(f"   micro-motion (detrended) std: src={va.std():.3f} out={vb.std():.3f} "
              f"ratio={vb.std() / (va.std() + 1e-9):.2f}")

    # per-30s segment pitch range to see whether climaxes survived
    seg = 30
    hop_s = 480 / 24000
    print("\nPER-SEGMENT PITCH RANGE (semitone p5..p95 span)")
    for t in range(0, int(n * hop_s), seg):
        i0, i1 = int(t / hop_s), int((t + seg) / hop_s)
        s_a, s_b = a[i0:i1], b[i0:i1]
        def span(x):
            v = x[x > 0]
            if len(v) < 20:
                return None
            st = 12 * np.log2(v / 440.0)
            return np.percentile(st, 95) - np.percentile(st, 5), np.median(st)
        ra, rb = span(s_a), span(s_b)
        if ra and rb:
            print(f"   {t:3d}s  src span={ra[0]:5.2f} med={ra[1]:7.2f} | "
                  f"out span={rb[0]:5.2f} med={rb[1]:7.2f}")


if __name__ == "__main__":
    main()
