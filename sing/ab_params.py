"""Compare RVC articulation under different protect / index-rate settings.

Same model, same input segment, three parameter sets, one concatenated wav with
0.5 s gaps so the result can be judged by ear in one pass. Also prints two
objective articulation proxies.

usage: python ab_params.py <vocal.wav> <start_sec> <dur_sec> [model] [index]
"""
import os
import shutil
import sys
import tempfile

import numpy as np
import soundfile as sf

RVC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RVC")
sys.path.insert(0, RVC)

import infer.cli as C  # noqa: E402  (chdir into the RVC project root)

src_path = sys.argv[1]
start = float(sys.argv[2]) if len(sys.argv) > 2 else 72.0
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 45.0
model_name = sys.argv[4] if len(sys.argv) > 4 else "yinyin.pth"
index_path = sys.argv[5] if len(sys.argv) > 5 else None

# (label, protect, index_rate)
VARIANTS = [
    ("A_current", 0.12, 0.95),
    ("B_default", 0.33, 0.75),
    ("C_clear", 0.50, 0.50),
]

x, sr = sf.read(src_path, dtype="float32", always_2d=True)
x = x.mean(axis=1)
a = int(start * sr)
b = min(int((start + dur) * sr), len(x))
seg = x[a:b]
print("segment %.1f-%.1f s  (%.1f s)" % (start, start + len(seg) / sr, len(seg) / sr))


def spectral_flux(y, sr_, n_fft=512, hop=160):
    win = np.hanning(n_fft).astype(np.float32)
    prev = None
    vals = []
    for i in range(0, len(y) - n_fft, hop):
        mag = np.abs(np.fft.rfft(y[i:i + n_fft] * win))
        if prev is not None:
            vals.append(float(np.sum(np.maximum(mag - prev, 0))))
        prev = mag
    return float(np.mean(vals)) if vals else 0.0


def hf_crest(y, sr_, lo=2000, hi=8000):
    """peak-to-average in the consonant band: higher = crisper transients"""
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y), 1 / sr_)
    m = (freqs >= lo) & (freqs < hi)
    if not m.any():
        return 0.0
    band = spec[m]
    return float(band.max() / (band.mean() + 1e-9))


model_path = C.resolve_model(model_name)
os.environ["weight_root"] = str(model_path.parent)
speaker_count, speakers = C.load_model_metadata(model_path)
sid = C.select_speaker(speaker_count, speakers, None)
idx = C.resolve_index(index_path, model_path.name, sid, 1.0)
print("model=%s index=%s" % (model_path.name, os.path.basename(idx)))

from infer.vc.modules import VC

config = C.create_config()
vc = VC(config)
vc.get_vc(model_path.name)

tmp = tempfile.mkdtemp(prefix="abparams_")
seg_path = os.path.join(tmp, "seg.wav")
sf.write(seg_path, seg, sr)

pieces = []
print("\n%-12s %-6s %-5s %-8s %-10s %-10s" % ("variant", "prot", "idx", "dur", "flux", "hf_crest"))
src_flux = spectral_flux(seg, sr)
src_crest = hf_crest(seg, sr)
print("%-12s %-6s %-5s %-8.1f %-10.4f %-10.2f" % ("source", "-", "-", len(seg) / sr, src_flux, src_crest))
for label, prot, ir in VARIANTS:
    status, result = vc.vc_single(sid, seg_path, 0, "rmvpe", idx, ir, 0, 1.0, prot)
    if not result or result[1] is None:
        print("%-12s FAILED" % label)
        print(status)
        continue
    out_sr, out = result
    out = np.asarray(out, dtype=np.float32)
    print("%-12s %-6.2f %-5.2f %-8.1f %-10.4f %-10.2f" % (
        label, prot, ir, len(out) / out_sr, spectral_flux(out, out_sr), hf_crest(out, out_sr)))
    pieces.append((label, out, out_sr))

shutil.rmtree(tmp, ignore_errors=True)
if not pieces:
    raise SystemExit("no output")

out_sr = pieces[0][2]
gap = np.zeros(int(0.5 * out_sr), dtype=np.float32)
chunks = []
for label, out, s in pieces:
    peak = float(np.abs(out).max())
    if peak > 0:
        out = out / peak * 0.9
    chunks.extend([out, gap])
final = np.concatenate(chunks)
dst = r"<PROJECT_ROOT>\sing\outputs\rvc\ab_params.wav"
sf.write(dst, final, out_sr)
print("\nwrote %s  %.1fs  (%s)" % (dst, len(final) / out_sr, " / ".join(p[0] for p in pieces)))

n16 = int(round(len(final) * 16000 / out_sr))
y16 = np.interp(np.linspace(0, len(final) - 1, n16), np.arange(len(final)), final).astype(np.float32)
open(r"<PROJECT_ROOT>\sing\outputs\rvc\ab_params.pcm", "wb").write((y16 * 32767).astype("<i2").tobytes())
print("pcm %.1fs" % (len(y16) / 16000))
