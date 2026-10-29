"""Isolate the source's highest-register passage and compare its timbre after
conversion -- that is where "唱不上去" would actually show up if it is real.
"""
import os
import sys

import numpy as np
import soundfile as sf

RVC = r"<PROJECT_ROOT>\sing\RVC"
sys.path.insert(0, RVC)
os.chdir(RVC)
os.environ.setdefault("rmvpe_root", os.path.join(RVC, "assets", "rmvpe"))
os.environ["HF_HUB_OFFLINE"] = "1"

from infer.rmvpe import RMVPE  # noqa: E402

SR = 16000
src_path, out_path, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
win_sec = float(sys.argv[4]) if len(sys.argv) > 4 else 12.0


def load(path, target=SR):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != target:
        n = int(round(len(x) * target / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x, sr


xs, sr_s = load(src_path)
model = RMVPE(os.path.join(RVC, "assets", "rmvpe", "rmvpe.pt"), is_half=False, device="cuda")
f0 = np.asarray(model.infer_from_audio(xs, thred=0.03), dtype=np.float32)
hop_ms = 16000 / 100 * 1  # rmvpe runs at 100 fps on 16k
fps = 100.0

w = int(win_sec * fps)
best = None
for i in range(0, max(len(f0) - w, 1), int(fps // 2)):
    seg = f0[i:i + w]
    v = seg[seg > 0]
    if len(v) < w * 0.5:
        continue
    score = float(np.percentile(v, 80))
    if best is None or score > best[0]:
        best = (score, i)
if best is None:
    raise SystemExit("no voiced window found")
score, i0 = best
t0 = i0 / fps
print("highest-register window: %.1fs - %.1fs  (p80 F0 = %.0f Hz)" % (t0, t0 + win_sec, score))

# cut the same span from both, at each file's native rate
for label, path in (("src", src_path), ("out", out_path)):
    x, sr = load(path, target=44100)
    a, b = int(t0 * sr), int((t0 + win_sec) * sr)
    seg = x[a:b]
    peak = float(np.abs(seg).max())
    if peak > 0:
        seg = seg / peak * 0.9
    dst = "%s_%s.wav" % (prefix, label)
    sf.write(dst, seg, sr)
    print("  wrote %s  %.1fs" % (dst, len(seg) / sr))
