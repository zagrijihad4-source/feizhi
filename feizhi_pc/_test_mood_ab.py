"""对比「害羞」档（新）与「傲娇」档（旧的静默回退）的实际语气差异。

用同一句话、同一个克隆音色，只看 style 指令带来的差别。
"""
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "……宝宝我好喜欢你啦，就这一遍啊，别让我说第二遍"

for mood in ("害羞", "傲娇", "温柔"):
    st = voice.style_for(mood)
    wav = tts.synthesize_wav(TEXT, style=st)
    p = OUT / ("K-档位对比-%s.wav" % mood)
    p.write_bytes(wav)
    print("%-4s %6d 字节  %.2f 秒  %s" % (mood, len(wav), len(wav) / 48000.0, p.name))
