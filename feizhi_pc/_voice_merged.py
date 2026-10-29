"""合并配方：教程结构 + U 系列的段内变化 + 高 guidance。

用户反馈：Z3（教程轻巧撒娇）比 Z1 好，但都不如 U2/U3（guidance 4/6）。
差别在 U 系列写了段内的前后变化（前半句亮、最后一句沉），教程配方只有整体定调。
这轮把两个优点合起来，看能不能超过 U3。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你终于回来啦！我等你好久了，刚才一直盯着手机看，你再不回我都要睡着了。"

# 合并版：情境 + 段内三拍变化（亮 → 埋怨 → 沉），无任何身份描述
MERGED = (
    "像等到很晚才听见他回来的动静：开口先一下子亮起来，声音往上扬；"
    "说到「等你好久」带点埋怨，语速快一些；"
    "最后那句「都要睡着了」声音低下去、有点委屈，尾音往下坠、变轻。"
    "前面亮，后面软，整段要有明显起伏，别一路平着说。"
)

CASES = [
    ("M1-合并-g4", TEXT, MERGED, 4.0),
    ("M2-合并-g6", TEXT, MERGED, 6.0),
    ("M3-合并-g8", TEXT, MERGED, 8.0),
]

for name, text, instr, g in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=g)
    (OUT / (name + ".wav")).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_m_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-14s %5.0f KB  指令 %d 字  g=%s" % (name, len(wav) / 1024.0, len(instr), g))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("M[123]-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    half = len(f0v)//2
    drift = (f0v[:half].mean() - f0v[half:].mean()) if half > 10 else 0.0
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-14s %5.2fs F0=%6.1f sd=%5.1f 前后差=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, f0v.mean(), f0v.std(), drift,
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
