"""向「最自然」那版收敛：低起伏、音高贴本底、过渡平滑。

用户点名 23:40 第一条（DD-真音-唱歌克隆，sd 37.9 / 帧间跳 4.0 / F0 202.5）最自然。
那一版是「改造前的温柔配方 + guidance 8」，但指标显示它起伏很小 ——
说明"自然"来自配方本身写得克制，不是 guidance 高。

这一轮试三组，目标是逼近 sd≈38、帧间跳≈4：
  I1 现温柔档 + guidance 2（降引导）
  I2 极平配方（只描述情绪不描述动作）+ guidance 3
  I3 无指令 + guidance 2（最保守，纯看模型默认）
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你今天几点睡的呀，我看你都困成这样了。"
VID = (tts.load_config().get("breeze") or {}).get("voice_id")

FLAT = (
    "像他说了句「我好累」，你心里软下来，说话就轻了。"
    "不用特别用力，也不用拖着调子，自然地说完就行。"
)

CASES = [
    ("I1-温柔g2", voice.style_for("温柔"), 2.0),
    ("I2-极平g3", FLAT, 3.0),
    ("I3-无指令g2", None, 2.0),
]

for name, st, g in CASES:
    wav = tts._breeze_synthesize(TEXT, st, VID, None, 90, guidance=g)
    p = OUT / (name + ".wav")
    p.write_bytes(wav)
    print("%-14s %5.0f KB" % (name, len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
d = Path(r"C:\Users\api62\Desktop\语音诊断")
items = [("目标(最自然那条)", d / "DD-真音-唱歌克隆.wav")]
items += [(p.stem, p) for p in sorted(d.glob("I[123]-*.wav"))]
for label, p in items:
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; f0v = f0[f0 > 0]
    d1 = np.abs(np.diff(f0v)) if len(f0v) > 2 else np.array([0.0])
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-18s %5.2fs F0=%6.1f sd=%5.1f 帧间跳=%4.1f 动态=%4.1f 静音=%4.1f%%"
          % (label, dur, f0v.mean(), f0v.std(), d1.mean(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
