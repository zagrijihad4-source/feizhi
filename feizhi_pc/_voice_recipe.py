"""按 GPT 教程的配方重测：指令里不带任何声音身份描述。

关键纠正（教程第 189 行）：声音身份由 voice_id 决定，instructions 里写
"19岁杭州女孩/美院大二/音色中低" 会让模型重新定义声线，把音色带偏。
我此前的 MOODS 八档每一条都带这些词。

这一轮：同一句台词，只比较「带身份描述的旧指令」vs「纯表演描述的新配方」。
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
TEXT = "你回来啦，我等你好久了。"
OLD = voice.style_for("温柔")     # 带身份描述

# 教程配方：温柔安慰（guidance 2 / speed 0.95）
WARM_NEW = "像安慰一个紧张的朋友，声音轻柔而稳，句尾自然放缓；让对方感到你会陪着他"
# 教程配方：轻巧撒娇（guidance 2 / speed 1）
CUTE_NEW = "像向熟悉的人提出一个小请求，语气柔和，带一点试探；句尾略微延长，情绪轻巧"

CASES = [
    ("Z1-旧指令-带身份", TEXT, OLD, 2.0, 1.0),
    ("Z2-教程温柔安慰", TEXT, WARM_NEW, 2.0, 0.95),
    ("Z3-教程轻巧撒娇", TEXT, CUTE_NEW, 2.0, 1.0),
]

for name, text, instr, g, sp in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=g, speed=sp)
    (OUT / (name + ".wav")).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_z_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-20s %5.0f KB  指令%3d字 g=%s speed=%s"
          % (name, len(wav) / 1024.0, len(instr), g, sp))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("Z[123]-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    best = cur = 0
    for v in voiced:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-20s %5.2fs 最长浊音=%4.2fs F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, best*0.01, f0v.mean(), f0v.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
