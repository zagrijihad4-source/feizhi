"""八档全部重写后的验收：同一句台词，逐档生成并量指标。

新配方要点（本轮确定）：
  * instructions 里不出现任何声音身份（年龄/职业/声线）；
  * 每档都写「情境开场 + 段内两到三拍变化 + 一句收束」；
  * guidance_scale = 8（用户实测选定的档）；
  * breeze 下 style_for 不再拼 mimo 的 RHYTHM / MOOD_RHYTHM。
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

print("provider =", tts.load_config().get("provider"))
print("guidance  =", (tts.load_config().get("breeze") or {}).get("guidance_scale"))
print()

for mood in voice.MOODS:
    st = voice.style_for(mood)
    wav = tts._breeze_synthesize(TEXT, st, None, None, 90)
    (OUT / ("A8-%s.wav" % mood)).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_a8_%s.pcm" % mood)
    tts.to_wechat_pcm(wav, pcm)
    print("%-4s 指令%3d字  %5.0f KB" % (mood, len(st), len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
rows = []
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("A8-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    half = len(f0v)//2
    drift = abs(f0v[:half].mean() - f0v[half:].mean()) if half > 10 else 0.0
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    rows.append((p.stem.replace("A8-",""), dur, f0v.mean(), f0v.std(), drift,
                 np.percentile(loud,95)-np.percentile(loud,5),
                 float(np.mean(db < db.max()-35))*100))
for name, dur, mean, sd, drift, dyn, sil in rows:
    print("%-4s %5.2fs F0=%6.1f sd=%5.1f 前后差=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (name, dur, mean, sd, drift, dyn, sil))
sd = [r[3] for r in rows]
print()
print("F0 sd 中位数 %.1f  最低 %.1f  最高 %.1f" % (np.median(sd), min(sd), max(sd)))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
