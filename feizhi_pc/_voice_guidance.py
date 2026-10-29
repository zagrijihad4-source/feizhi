"""关键变量：guidance_scale。

官方 cURL 示例用的是 4.0，而 schema 默认是 1.0 —— 我此前大部分实验都在默认值下跑，
instructions 基本没被吃进去。这一轮把它拉起来，同时换一句更有情绪张力的文本
（用户指出「是说的话的问题」）。
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

# 有情绪张力的文本：期待 + 埋怨 + 委屈收尾，不是平的陈述
TEXT = "你终于回来啦！我等你好久了，刚才一直盯着手机看……你再不回我都要睡着了。"

WARM = voice.style_for("温柔")           # 现用档位
OUT_SPOKEN = (
    "她等了他很久，终于听见动静，先是一下子高兴起来，声音往上扬、亮起来；"
    "说到「等你好久」带点埋怨，语速快一点；"
    "最后那句「都要睡着了」声音低下去，有点委屈，尾音往下坠、变轻。"
    "整段要有明显的起伏：前面亮，后面软。不要一路平着说，也不要用同一种情绪说完。"
)

CASES = [
    ("U1-温柔档-g4", TEXT, WARM, 4.0),
    ("U2-起伏设计-g4", TEXT, OUT_SPOKEN, 4.0),
    ("U3-起伏设计-g6", TEXT, OUT_SPOKEN, 6.0),
]

for name, text, instr, g in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=g)
    p = OUT / (name + ".wav")
    p.write_bytes(wav)
    pcm = ROOT / "tmp" / ("_u_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-18s %5.0f KB  guidance=%s" % (name, len(wav) / 1024.0, g))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
CH = 33
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("U*.wav")):
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
    # 前后半段的 F0 差，衡量"有没有起伏变化"
    half = len(f0)//2
    drift = (f0[:half].mean() - f0[half:].mean()) if half > 10 else 0.0
    print("%-18s %5.2fs %4.2f字/秒 F0=%6.1f sd=%5.1f 前后差=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, CH/dur, f0.mean(), f0.std(), drift,
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
