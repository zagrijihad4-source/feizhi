"""量第一轮对照的客观指标，并把两条候选发到微信。

人机感的可计算代理：
  * 时长 / 字速：太快像播报，太慢像念稿；
  * F0 标准差：语调起伏，过低=平，过高=演戏；
  * 动态（dB p95-p5）：有没有轻重；
  * 停顿占比：静音太多就碎。
"""
import subprocess
import sys
from pathlib import Path

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

ANALYZE = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("M-*.wav")):
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
    silent = float(np.mean(db < db.max() - 35))
    chars = 24
    print("%-16s %5.2fs  %.2f字/秒  F0=%6.1f sd=%5.1f  动态=%4.1f  静音=%4.1f%%"
          % (p.stem.replace("M-", ""), dur, chars / dur, f0.mean(), f0.std(),
             np.percentile(loud, 95) - np.percentile(loud, 5), silent * 100))
'''

r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", ANALYZE],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
