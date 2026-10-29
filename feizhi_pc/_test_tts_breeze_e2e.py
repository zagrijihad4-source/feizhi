"""端到端验证：breeze 已成为第一优先级，且能产出微信可用的 16k PCM。"""
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

cfg = tts.load_config()
print("provider =", cfg.get("provider"))
print("breeze.voice_id =", (cfg.get("breeze") or {}).get("voice_id"))
print("voices() =", tts.voices())
print()

TEXT = "你今天到底几点睡的，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。"
STYLE = voice.style_for("傲娇")

wav = tts.synthesize_wav(TEXT, style=STYLE)
print("synthesize_wav: %d 字节  头=%r" % (len(wav), wav[:4]))
if wav[:4] != b"RIFF":
    print("!! 不是 wav，to_wechat_pcm 会出问题")
else:
    with wave.open(__import__("io").BytesIO(wav)) as w:
        print("   %.2f 秒  %d Hz  %d ch" % (
            w.getnframes() / float(w.getframerate()),
            w.getframerate(), w.getnchannels()))

pcm = tts.synthesize_pcm(TEXT, style=STYLE)
size = pcm.stat().st_size
print()
print("synthesize_pcm:", pcm.name, "%d 字节 = %.2f 秒 @16k mono s16le"
      % (size, size / 32000.0))
print("文件存在:", pcm.exists(), " 目录:", pcm.parent)
