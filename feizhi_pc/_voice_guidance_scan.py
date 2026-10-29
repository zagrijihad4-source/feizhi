"""guidance_scale 对音色保真度的影响。

音色换了之后，guidance 8 可能导致过度表演——文档的排查表里，
"过度表演、每个字都用力"的处方是删形容词 + 降低 guidance。
这一轮固定档位（温柔/开心）与音色，只扫 guidance。
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

# 本底：无指令（作为音高基准）
base = tts._breeze_synthesize(TEXT, None, VID, None, 90)
(OUT / "G0-本底.wav").write_bytes(base)

for mood in ("温柔", "开心"):
    st = voice.style_for(mood)
    for g in (2.0, 4.0, 8.0):
        wav = tts._breeze_synthesize(TEXT, st, VID, None, 90, guidance=g)
        outp = OUT / ("G0-%s-g%d.wav" % (mood, int(g)))
        outp.write_bytes(wav)
        print("%-4s g=%-4s %5.0f KB" % (mood, g, len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
d = Path(r"C:\Users\api62\Desktop\语音诊断")
base = None
items = [d / "G0-本底.wav"] + sorted(d.glob("G0-*-g*.wav"))
for p in items:
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; f0v = f0[f0 > 0]
    mean = f0v.mean()
    if base is None:
        base = mean
        print("%-14s %5.2fs F0=%6.1f (基准) sd=%5.1f" % (p.stem, dur, mean, f0v.std()))
        continue
    dev = (mean - base) / base * 100
    flag = "  <== 音色跑掉" if abs(dev) > 12 else ""
    print("%-14s %5.2fs F0=%6.1f 偏离=%+5.1f%% sd=%5.1f%s"
          % (p.stem, dur, mean, dev, f0v.std(), flag))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
