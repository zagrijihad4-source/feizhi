"""对比用户点名的"最自然"那条（23:40 第一条）与当前版本。

23:40 发送顺序：
  1. DD-真音-唱歌克隆.wav   ← 用户说这条最自然
  2. DD-新-MiMo参考克隆.wav
当时参数：voc_z4npxsc7ch8m + 改造前的温柔配方 + guidance 8

当前（23:49）：H0-温柔-0.wav = 同音色 + 改造后的温柔配方 + guidance 3
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(r"C:\Users\api62\Desktop\语音诊断")

for p in sorted(D.glob("*.wav")):
    if p.name.startswith(("DD-", "H0-温柔", "H0-base", "G0-本底", "F0-本底")):
        print("%-26s %6.0f KB" % (p.name, p.stat().st_size / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
d = Path(r"C:\Users\api62\Desktop\语音诊断")
TARGETS = [
    ("23:40 第1条(用户说最自然)", "DD-真音-唱歌克隆.wav"),
    ("当前温柔(g3+新配方)",       "H0-温柔-0.wav"),
    ("g8 旧配方那版",             "E8-温柔.wav"),
]
for label, name in TARGETS:
    p = d / name
    if not p.exists():
        print("%-26s 缺文件" % label); continue
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    # 逐帧 F0 变化速度（越大越跳）
    d1 = np.abs(np.diff(f0v)) if len(f0v) > 2 else np.array([0])
    print("%-26s %5.2fs F0=%6.1f sd=%5.1f 帧间跳=%4.1f 动态=%4.1f 静音=%4.1f%%"
          % (label, dur, f0v.mean(), f0v.std(), d1.mean(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
