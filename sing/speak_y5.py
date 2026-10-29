"""Render a spoken line through the yinyin5 model and export it as WeChat PCM."""
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

SING = r"<PROJECT_ROOT>\sing"
sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import tts  # noqa: E402

SPOKEN = ("嗯，我在呢。今天挺累的吧，我看你从早到晚一直在忙那个海报。"
          "先别管它了，歇一会儿。我给你讲点别的，你别老一个人闷着。")

OUT = os.path.join(SING, "outputs", "rvc")
os.makedirs(OUT, exist_ok=True)

print("[1/3] TTS")
pcm = tts.synthesize_pcm(SPOKEN, style="平静、像在跟人随口说话")
raw = np.fromfile(str(pcm), dtype="<i2").astype(np.float32) / 32768.0
src_wav = os.path.join(OUT, "speak_src.wav")
sf.write(src_wav, raw, 16000)
print("  %.1fs" % (len(raw) / 16000))

print("[2/3] RVC -> yinyin5")
py = os.path.join(SING, ".venv", "Scripts", "python.exe")
env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
conv = os.path.join(OUT, "speak_y5.wav")
r = subprocess.run([py, "-u", os.path.join(SING, "rvc_cover.py"), src_wav, conv,
                    "--model", "yinyin5.pth", "--index-rate", "0", "--protect", "0.5"],
                   cwd=SING, env=env, capture_output=True, text=True,
                   encoding="utf-8", errors="ignore", timeout=600,
                   creationflags=0x08000000)
print("  rc=%s" % r.returncode)
if not os.path.exists(conv):
    print((r.stdout or "")[-400:], (r.stderr or "")[-300:])
    sys.exit(1)

print("[3/3] to 16k PCM")
x, sr = sf.read(conv, dtype="float32", always_2d=True)
x = x.mean(axis=1)
x = x / max(float(np.abs(x).max()), 1e-9) * 0.92
n16 = int(round(len(x) * 16000 / sr))
y = np.interp(np.linspace(0, len(x) - 1, n16), np.arange(len(x)), x).astype(np.float32)
dst = os.path.join(OUT, "speak_y5.pcm")
open(dst, "wb").write((y * 32767).astype("<i2").tobytes())
print("  %s  %.1fs" % (dst, len(y) / 16000))
