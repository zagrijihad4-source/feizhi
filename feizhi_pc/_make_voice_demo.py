import sys
from pathlib import Path
sys.path.insert(0, ".")
import tts, voice

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
OUT.mkdir(parents=True, exist_ok=True)
CASES = [
    ("ZZ1-varied-开心", "真的假的！你居然还记得呀……我还以为你早忘了。", "开心"),
    ("ZZ2-varied-温柔", "宝宝，我在呢。刚在改稿子。听见你叫我就过来了。", "温柔"),
    ("ZZ3-plain-开心", "真的假的！你居然还记得呀……我还以为你早忘了。", None),
]
for tag, text, mood in CASES:
    style = voice.style_for(mood) if mood else None
    wav = tts.synthesize_wav(text, style=style)
    p = OUT / ("%s.wav" % tag)
    p.write_bytes(wav)
    print("%-18s %6d 字节  %s" % (tag, len(wav), p))
