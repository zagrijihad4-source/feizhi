"""更极端的拖长写法：多根破折号 / 语气词带拖 / 字重复。

上一轮证明省略号会把长音切成"断"，破折号好一些但还没够。
这一轮只动那一个字附近的写法，其余全部固定（guidance 5.0，同一段指令）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
INSTR = (
    "她等了他很久，终于听见动静：先一下子高兴起来，声音往上扬、亮起来；"
    "说到「等你好久」带点埋怨，语速快；最后一句声音低下去、有点委屈，尾音往下坠。"
    "前面亮，后面软。"
)

VARIANTS = [
    ("W1-三破折号", "你终于回来啦！我等你好久了，刚才一直盯着手机看———你再不回我都要睡着了。"),
    ("W2-啊拖长", "你终于回来啦！我等你好久了，刚才一直盯着手机看啊————你再不回我都要睡着了。"),
    ("W3-字重复", "你终于回来啦！我等你好久了，刚才一直盯着手机看看看看——你再不回我都要睡着了。"),
]

for name, text in VARIANTS:
    wav = tts._breeze_synthesize(text, INSTR, None, None, 90, guidance=5.0)
    (OUT / (name + ".wav")).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_w_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-14s %5.0f KB" % (name, len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("W[123]-*.wav")):
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
    print("%-14s %5.2fs  最长连续浊音=%4.2fs  F0 sd=%5.1f"
          % (p.stem, dur, best * 0.01, f0v.std()))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
