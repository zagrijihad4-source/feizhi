import sys
from pathlib import Path
sys.path.insert(0, ".")
import tts

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
OUT.mkdir(parents=True, exist_ok=True)
TEXT = "宝宝，我在呢。刚在改稿子。听见你叫我就过来了。"

CASES = [
    ("AAA-明快", "说话轻快明亮，语速偏快一点，尾音带笑意，像刚遇到件好事。"),
    ("BBB-带笑", "说话轻快明亮，语速正常，中间忍不住笑出声来，笑完接着说。"),
]
for tag, instr in CASES:
    wav = tts.synthesize_wav(TEXT, style=instr)
    p = OUT / ("%s.wav" % tag)
    p.write_bytes(wav)
    print("%-10s %6d 字节" % (tag, len(wav)))
print()
print("对照参考：ZZ2-varied-温柔.wav（你说比较好的那个）")
