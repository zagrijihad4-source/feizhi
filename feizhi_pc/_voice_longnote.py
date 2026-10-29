"""省略号 vs 破折号 vs 指令指定，哪种才能真的拖出长音。

用户反馈：「……」被模型理解成短收，本该是长音的地方变成了短音。
中文里拖长的常规写法是破折号，或者直接在 instructions 里点명某个字拖。
三种都试，其余参数固定（guidance 5.0，起伏设计指令）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

BASE = (
    "她等了他很久，终于听见动静：先一下子高兴起来，声音往上扬、亮起来；"
    "说到「等你好久」带点埋怨，语速快；最后一句声音低下去、有点委屈，尾音往下坠。"
    "前面亮，后面软，不要一路平着说。"
)
WITH_LONG = BASE + "「盯着手机看」的「看」字要拖长，拖出等得发慌的感觉。"

VARIANTS = [
    ("V1-省略号", "你终于回来啦！我等你好久了，刚才一直盯着手机看……你再不回我都要睡着了。", BASE),
    ("V2-破折号", "你终于回来啦！我等你好久了，刚才一直盯着手机看——你再不回我都要睡着了。", BASE),
    ("V3-指令点명", "你终于回来啦！我等你好久了，刚才一直盯着手机看，你再不回我都要睡着了。", WITH_LONG),
]

for name, text, instr in VARIANTS:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=5.0)
    p = OUT / (name + ".wav")
    p.write_bytes(wav)
    pcm = ROOT / "tmp" / ("_v_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-14s %5.0f KB  文本 %d 字" % (name, len(wav) / 1024.0, len(text)))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("V[123]-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    # 最长连续浊音段（近似"最长一个长音"）
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
