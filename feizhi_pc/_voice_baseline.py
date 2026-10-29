"""建立音色基准：同一音色、中性文本、不同指令下的音高偏离。

教训（2026-10-27）：我一直用 F0 标准差当"情感"指标，把失真当表现力。
开心档 F0 均值 473、心虚 446，而温柔 228 —— 同一音色音高翻倍，声线已经换了人。
以后任何档位的判断必须同时看：
  * 音高偏离：相对本底的 F0 均值偏差，超过 ~12% 就是音色跑掉了；
  * 时长：同一句话不应因为情绪而膨胀一倍。
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
VID = (tts.load_config().get("breeze") or {}).get("voice_id")

# 本底声线：完全不给指令，让模型用它对这个音色的默认理解去读
base = tts._breeze_synthesize(TEXT, None, VID, None, 90)
(OUT / "F0-本底.wav").write_bytes(base)
print("本底样本已生成 %d KB" % (len(base) // 1024))

A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
paths = [Path(r"C:\Users\api62\Desktop\语音诊断\F0-本底.wav")]
paths += sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("E8-*.wav"))
base = None
for p in paths:
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; f0v = f0[f0 > 0]
    mean = f0v.mean()
    if base is None:
        base = mean
    dev = (mean - base) / base * 100
    flag = ""
    if abs(dev) > 12:
        flag = "  <== 音色跑掉"
    print("%-8s %5.2fs F0=%6.1f 偏离=%+5.1f%% sd=%5.1f%s"
          % (p.stem, dur, mean, dev, f0v.std(), flag))
print()
print("本底 F0 = %.1f Hz" % base)
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
