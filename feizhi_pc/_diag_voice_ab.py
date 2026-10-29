"""量化三组语音样本的情感指标差异。

要回答的问题：平淡是「克隆模型」造成的，还是「style 指令」造成的。
如果 A（克隆）和 B（预设音色）指标接近 → 克隆不是元凶；
如果 C（强 style）明显比 A 活 → 情感主要来自 style 指令的质量。
"""
import sys
from pathlib import Path

import numpy as np
import parselmouth
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")

DIR = Path(r"C:\Users\api62\Desktop\语音诊断")


def stats(path):
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pitch = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    frame = max(1, int(sr * 0.02))
    n = len(x) // frame
    rms = np.array([np.sqrt(np.mean(x[i * frame:(i + 1) * frame] ** 2) + 1e-12)
                    for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    dyn = float(np.percentile(loud, 95) - np.percentile(loud, 5)) if len(loud) > 4 else 0.0
    silent = float(np.mean(db < db.max() - 35))
    hist, _ = np.histogram(f0, bins=np.arange(75, 605, 10))
    top = float(hist.max() / hist.sum()) if len(f0) > 10 else 0.0
    # 语速：有效音节数用 F0 段数近似
    voiced = f0 > 0
    segs = int(np.sum(np.diff(voiced.astype(int)) == 1)) + (1 if voiced.any() else 0)
    return dict(dur=dur, mean=f0.mean(), sd=f0.std(), lo=f0.min(), hi=f0.max(),
                dyn=dyn, silent=silent, top=top, segs=segs)


print("%-24s %6s %7s %7s %7s %7s %7s" % ("样本", "时长", "F0均值", "F0 sd", "动态dB", "静音%", "集中度"))
rows = {}
for p in sorted(DIR.glob("*.wav")):
    s = stats(p)
    rows[p.stem[:1]] = s
    print("%-24s %5.1fs %7.1f %7.1f %7.1f %6.1f%% %7.2f"
          % (p.stem[:22], s["dur"], s["mean"], s["sd"], s["dyn"],
             s["silent"] * 100, s["top"]))

if "A" in rows and "B" in rows:
    print()
    print("A(克隆) vs B(预设音色)：F0 sd %.1f vs %.1f，动态 %.1f vs %.1f"
          % (rows["A"]["sd"], rows["B"]["sd"], rows["A"]["dyn"], rows["B"]["dyn"]))
if "A" in rows and "C" in rows:
    print("A(原style) vs C(强style)：F0 sd %.1f vs %.1f，动态 %.1f vs %.1f"
          % (rows["A"]["sd"], rows["C"]["sd"], rows["A"]["dyn"], rows["C"]["dyn"]))
