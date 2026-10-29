"""校准 speed 语义 + 找「不漫不经心」的语速档。

背景：用户反馈「语速太慢，显得漫不经心」。
之前 C 组 speed=0.9 反而比默认更短，怀疑 speed 不是"语速倍率"而是别的含义，
所以先做一次干净的校准：同文本同指令，只改 speed，量时长。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你今天几点睡的呀，眼睛都睁不开了吧，还嘴硬说没困。"   # 24 字，不含标签
CHARS = 24

# 指令：只留"往上挑 + 笑到一半收住"这两个具体动作，不提"接得紧"也不提任何速度词，
# 让 speed 成为唯一变量。
INSTR = (
    "说的时候声音是软的、带黏，像刚靠过来贴着人说话。"
    "前半句带着埋怨，「几点睡的」往上挑一下；"
    "说到「还嘴硬」忍不住笑出来，笑到一半收住。"
)

CASES = [("s10", 1.0), ("s13", 1.3), ("s16", 1.6), ("s07", 0.7)]

for name, sp in CASES:
    wav = tts._breeze_synthesize(TEXT, INSTR, None, None, 90, speed=sp)
    p = OUT / ("P-%s.wav" % name)
    p.write_bytes(wav)
    print("%-5s speed=%-4s %5.0f KB" % (name, sp, len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
CH = 24
rows = []
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("P-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; f0 = f0[f0 > 0]
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    rows.append((p.stem, dur, CH/dur, f0.std(), float(np.mean(db < db.max()-35))*100))
for name, dur, rate, sd, sil in rows:
    print("%-8s %5.2fs  %4.2f字/秒  F0sd=%5.1f  静音=%4.1f%%" % (name, dur, rate, sd, sil))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
