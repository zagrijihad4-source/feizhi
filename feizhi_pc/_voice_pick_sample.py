"""挑一段最有起伏的真实人声，作为新的克隆样本。

现用样本 feizhi_B_sample.wav 是 voicedesign 合成的「冷清慵懒」，不是音音子本人录音，
F0 sd 只有 55.2 —— 克隆会把这个平韵律学过去，这是「怎么调都平淡」的上限所在。
真实素材在 source/sep_test/yy_*_vocal.wav（分离后无伴奏）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\sing")
sys.stdout.reconfigure(encoding="utf-8")

A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
cands = sorted(Path(r"<PROJECT_ROOT>\sing\source\sep_test").glob("*_vocal.wav"))
cands += sorted(Path(r"<PROJECT_ROOT>\sing\source\batch").glob("yy_0[0-3].wav"))
for p in cands:
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.02, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; f0v = f0[f0 > 0]
    fr = max(1, int(sr * 0.05)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-22s %5.1fs %5.0fkHz F0=%6.1f sd=%5.1f 动态=%4.1f 浊音比=%3.0f%%"
          % (p.name, dur, sr/1000, f0v.mean() if len(f0v) else 0,
             f0v.std() if len(f0v) else 0,
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(f0 > 0))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
print()
print("参考：现用合成样本 feizhi_B_sample 是 F0 sd=55.2")
