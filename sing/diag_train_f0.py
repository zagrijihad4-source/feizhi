"""What registers did the model actually see during training?

rmvpe-based, so the histogram is trustworthy: autocorrelation over-reports high
frames by locking onto harmonics, which would make the data look better than it is.
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

exp = sys.argv[1] if len(sys.argv) > 1 else "yinyin"
files = sorted(glob.glob(os.path.join("logs", exp, "0_gt_wavs", "*.wav")))
if not files:
    raise SystemExit("no slices in logs/%s/0_gt_wavs" % exp)

model = RMVPE(os.path.join(RVC, "assets", "rmvpe", "rmvpe.pt"), is_half=False, device="cuda")

allf = []
for f in files:
    x, sr = sf.read(f, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000:
        n = int(round(len(x) * 16000 / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    f0 = np.asarray(model.infer_from_audio(x, thred=0.03), dtype=np.float32)
    allf.append(f0)
    if len(allf) % 20 == 0:
        print("  analysed %d/%d" % (len(allf), len(files)), flush=True)

f0 = np.concatenate(allf)
v = f0[f0 > 0]
print("\nslices: %d   voiced frames: %d (%.1f%%)" % (len(files), len(v), 100.0 * len(v) / len(f0)))
vals = [float(np.percentile(v, q)) for q in (5, 25, 50, 75, 90, 95, 99)] + [float(v.max())]
print("percentiles: p5 %.0f  p25 %.0f  p50 %.0f  p75 %.0f  p90 %.0f  p95 %.0f  p99 %.0f  max %.0f"
      % tuple(vals))

print("\nhow much material exists per register:")
for lo, hi in [(0, 200), (200, 300), (300, 400), (400, 500), (500, 600), (600, 800), (800, 1100), (1100, 1400)]:
    m = (v >= lo) & (v < hi)
    bar = "#" * int(60 * m.sum() / max(len(v), 1))
    print("  %4d-%4d Hz  %5.1f%%  %s" % (lo, hi, 100.0 * m.sum() / max(len(v), 1), bar))
