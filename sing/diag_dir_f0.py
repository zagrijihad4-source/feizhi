"""Scan a folder of vocals and report how much material exists in each register.

Written for the question "do we have any high-register singing to train on?"
usage: python diag_dir_f0.py <folder> [top_n]
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

RVC = r"<PROJECT_ROOT>\sing\RVC"
sys.path.insert(0, RVC)
os.chdir(RVC)
os.environ.setdefault("rmvpe_root", os.path.join(RVC, "assets", "rmvpe"))

from infer.rmvpe import RMVPE  # noqa: E402

folder = sys.argv[1]
top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
files = sorted(glob.glob(os.path.join(folder, "*.wav")))
if not files:
    raise SystemExit("no wav in %s" % folder)

model = RMVPE(os.path.join(RVC, "assets", "rmvpe", "rmvpe.pt"), is_half=False, device="cuda")

per_file = []
allf = []
for i, f in enumerate(files):
    try:
        x, sr = sf.read(f, dtype="float32", always_2d=True)
    except Exception:  # noqa: BLE001
        continue
    x = x.mean(axis=1)
    if sr != 16000:
        n = int(round(len(x) * 16000 / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    f0 = np.asarray(model.infer_from_audio(x, thred=0.03), dtype=np.float32)
    v = f0[f0 > 0]
    if len(v) < 30:
        continue
    allf.append(v)
    per_file.append((float(np.percentile(v, 95)), float(v.max()), os.path.basename(f), len(v)))
    if (i + 1) % 20 == 0:
        print("  %d/%d" % (i + 1, len(files)), flush=True)

v = np.concatenate(allf) if allf else np.array([])
print("\nfiles with voice: %d   voiced frames: %d" % (len(allf), len(v)))
vals = [float(np.percentile(v, q)) for q in (5, 50, 90, 95, 99)] + [float(v.max())]
print("percentiles: p5 %.0f  p50 %.0f  p90 %.0f  p95 %.0f  p99 %.0f  max %.0f" % tuple(vals))

print("\nregister coverage:")
for lo, hi in [(0, 200), (200, 300), (300, 400), (400, 500), (500, 600), (600, 800), (800, 1100)]:
    m = (v >= lo) & (v < hi)
    print("  %4d-%4d Hz  %5.1f%%  %s" % (lo, hi, 100.0 * m.sum() / max(len(v), 1),
                                          "#" * int(58 * m.sum() / max(len(v), 1))))

per_file.sort(reverse=True)
print("\ntop %d highest clips (p95 F0):" % top_n)
for p95, mx, name, n in per_file[:top_n]:
    print("  p95 %6.1f Hz  max %6.1f Hz  %s" % (p95, mx, name))
