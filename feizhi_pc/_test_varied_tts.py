import sys, time
from pathlib import Path
sys.path.insert(0, ".")
import tts, voice

TEXT = "真的假的！你居然还记得呀……我还以为你早忘了。"
for tag, style in (("开心", voice.style_for("开心")),):
    t0 = time.time()
    pcm = tts.synthesize_pcm(TEXT, style=style)
    el = time.time() - t0
    size = Path(pcm).stat().st_size
    print("%s：合成 %.1fs -> %.2fs 音频（%d 样本）%s"
          % (tag, el, size / 32000.0, size // 2, Path(pcm).name))
