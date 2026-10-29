"""Rebuild the RVC v2 training set without the data loss of the stock pipeline.

Why this exists
---------------
RVC's own train/preprocess.py hard-cuts every slice into fixed 3.7 s windows and
its output then got concatenated by build_all_voice.py, which kept only ~10 s out
of each 22 s recording (417.9 s -> 190 s). It also produced a 190 s hard-glued
file, so a slice could straddle a join between two different recordings.

What this does instead
----------------------
- processes each source recording independently (no cross-recording joins)
- slices on natural pauses with RVC's own Slicer (same params as upstream)
- keeps everything between 2 s and 10 s; anything longer is split at the
  quietest interior point rather than at a fixed offset
- resamples with a polyphase filter to 40 kHz (model rate) and 16 kHz (for
  F0 / HuBERT extraction)
- gentle peak normalisation only (no denoise, no dynamics processing)
- de-duplicates near-identical slices, drops clipping and dead air
- writes a per-file report so every second can be accounted for

usage: python rebuild_trainset.py [exp_name] [--validate-ratio 0.1]
"""
import argparse
import hashlib
import json
import os
import sys
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal as sps

RVC = Path(r"<PROJECT_ROOT>\sing\RVC")
sys.path.insert(0, str(RVC))
os.chdir(RVC)
os.environ.setdefault("rmvpe_root", str(RVC / "assets" / "rmvpe"))

from train.dataset.slicer2 import Slicer  # noqa: E402

BATCH = Path(r"<PROJECT_ROOT>\sing\source\batch")
MODEL_SR = 40000
FEAT_SR = 16000
MIN_SEC, MAX_SEC = 2.0, 6.0
# RVC's DistributedBucketSampler keeps only samples whose
#   length = getsize(wav) // (3 * hop_length)
# falls inside boundaries [100 .. 900]; anything longer is silently discarded.
# At 40 kHz float32 that ceiling is ~6.75 s, so slices must stay under it.
MAX_PEAK = 0.95          # drop slices hotter than this (already clipped)
MIN_RMS = 0.004          # drop dead air
NORM_PEAK = 0.85         # gentle target, matches RVC's own intent


def resample(x, sr_from, sr_to):
    if sr_from == sr_to:
        return x.astype(np.float32)
    g = gcd(int(sr_from), int(sr_to))
    return sps.resample_poly(x, sr_to // g, sr_from // g).astype(np.float32)


def load_mono(path):
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if x.shape[1] > 1:
        x = x.mean(axis=1)
    else:
        x = x[:, 0]
    return x, sr


def split_long(a, sr, max_sec):
    """Split at the quietest interior point instead of a fixed offset."""
    pieces = []
    i = 0
    while (len(a) - i) / sr > max_sec:
        target = i + int(max_sec * sr)
        lo = max(i + int(MIN_SEC * 0.6 * sr), target - int(1.5 * sr))
        hi = min(len(a) - int(MIN_SEC * 0.6 * sr), target)
        seg = np.abs(a[lo:hi])
        # 20 ms envelope, pick its minimum as the cut point
        w = max(int(0.02 * sr), 1)
        env = np.convolve(seg, np.ones(w) / w, mode="same")
        cut = lo + int(np.argmin(env)) if len(env) else target
        pieces.append(a[i:cut])
        i = cut
    pieces.append(a[i:])
    return [p for p in pieces if len(p) / sr >= MIN_SEC * 0.6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp", nargs="?", default="yinyin4")
    ap.add_argument("--sources", default=str(BATCH))
    ap.add_argument("--validate-ratio", type=float, default=0.12)
    args = ap.parse_args()

    exp_dir = RVC / "logs" / args.exp
    gt = exp_dir / "0_gt_wavs"
    g16 = exp_dir / "1_16k_wavs"
    for d in (gt, g16):
        d.mkdir(parents=True, exist_ok=True)

    sources = sorted(Path(args.sources).glob("*.wav"))
    if not sources:
        raise SystemExit("no *.wav in %s" % args.sources)

    report = {"sources": [], "slices": [], "dropped": []}
    seen = {}
    total_src = 0.0
    total_keep = 0.0

    for src in sources:
        x, sr = load_mono(src)
        total_src += len(x) / sr
        x40 = resample(x, sr, MODEL_SR)

        slicer = Slicer(sr=MODEL_SR, threshold=-42, min_length=1500,
                        min_interval=400, hop_size=15, max_sil_kept=500)
        kept = 0
        src_info = {"file": src.name, "src_sec": round(len(x) / sr, 3),
                    "src_rate": sr, "slices": [], "kept_sec": 0.0}

        for piece in slicer.slice(x40):
            for seg in split_long(piece, MODEL_SR, MAX_SEC):
                dur = len(seg) / MODEL_SR
                peak = float(np.abs(seg).max())
                rms = float(np.sqrt(np.mean(seg * seg)))
                if dur < MIN_SEC:
                    report["dropped"].append({"file": src.name, "why": "too_short", "sec": round(dur, 3)})
                    continue
                if peak > MAX_PEAK:
                    report["dropped"].append({"file": src.name, "why": "clipping", "peak": round(peak, 3),
                                              "sec": round(dur, 3)})
                    continue
                if rms < MIN_RMS:
                    report["dropped"].append({"file": src.name, "why": "silent", "rms": round(rms, 5)})
                    continue
                key = hashlib.sha1(np.round(seg[::97] * 1000).astype(np.int16).tobytes()).hexdigest()[:16]
                if key in seen:
                    report["dropped"].append({"file": src.name, "why": "duplicate_of_" + seen[key]})
                    continue
                seen[key] = src.name

                out = seg / peak * NORM_PEAK
                idx = len(src_info["slices"])
                name = "%s_s%02d" % (src.stem, idx)
                sf.write(str(gt / (name + ".wav")), out, MODEL_SR, subtype="FLOAT")
                sf.write(str(g16 / (name + ".wav")), resample(out, MODEL_SR, FEAT_SR), FEAT_SR, subtype="FLOAT")

                src_info["slices"].append({"name": name, "sec": round(dur, 2),
                                           "peak": round(peak, 3), "rms": round(rms, 4)})
                kept += 1

        src_info["kept_sec"] = round(sum(s["sec"] for s in src_info["slices"]), 2)
        total_keep += src_info["kept_sec"]
        report["sources"].append(src_info)
        print("%-12s %6.2fs -> %2d slices  %6.2fs kept (%.0f%%)"
              % (src.name, src_info["src_sec"], kept, src_info["kept_sec"],
                 100.0 * src_info["kept_sec"] / max(src_info["src_sec"], 1e-9)))

    # hold out whole recordings for validation so the same take never sits on both sides
    n_val = max(1, int(round(len(report["sources"]) * args.validate_ratio)))
    val = sorted(report["sources"], key=lambda r: r["file"])[-n_val:]
    val_names = {r["file"] for r in val}
    train_lines, val_lines = [], []
    for r in report["sources"]:
        rows = val_lines if r["file"] in val_names else train_lines
        for s in r["slices"]:
            rows.append(s["name"])

    report["summary"] = {
        "sources": len(sources),
        "source_sec": round(total_src, 2),
        "kept_sec": round(total_keep, 2),
        "utilization": round(100.0 * total_keep / max(total_src, 1e-9), 1),
        "slices": sum(len(r["slices"]) for r in report["sources"]),
        "dropped": len(report["dropped"]),
        "train_slices": len(train_lines),
        "val_slices": len(val_lines),
        "model_sr": MODEL_SR,
        "feat_sr": FEAT_SR,
    }
    report["split"] = {"train": train_lines, "val": val_lines}
    (exp_dir / "dataset_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (exp_dir / "val_slices.txt").write_text("\n".join(sorted(val_lines)), encoding="utf-8")

    s = report["summary"]
    print("\n=== summary ===")
    print("source %.1fs -> kept %.1fs (%.1f%%)  slices %d  dropped %d"
          % (s["source_sec"], s["kept_sec"], s["utilization"], s["slices"], s["dropped"]))
    print("train %d slices / val %d slices (hold-out recordings: %s)"
          % (s["train_slices"], s["val_slices"], ", ".join(sorted(val_names))))
    print("-> %s" % exp_dir)


if __name__ == "__main__":
    main()
