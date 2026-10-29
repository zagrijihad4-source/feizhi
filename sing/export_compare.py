"""Export the three-way comparison as standalone audio files at best quality.

Not the 16 kHz WeChat voice path -- these keep each source's native rate so the
timbre comparison is not polluted by resampling.
"""
import os

import numpy as np
import soundfile as sf

OUT = r"<PROJECT_ROOT>\sing\outputs\compare"
os.makedirs(OUT, exist_ok=True)

START, DUR = 83.0, 45.0

jobs = [
    ("01-原唱-潮汐.wav", r"<PROJECT_ROOT>\sing\source\taoxi.wav", START, DUR),
    ("02-模型说话.wav", r"<PROJECT_ROOT>\sing\outputs\rvc\cmp2_spoken_yinyin.wav", None, None),
    ("03-模型唱歌-潮汐.wav", r"<PROJECT_ROOT>\sing\outputs\rvc\taoxi_hi_mix.wav", START, DUR),
]

for name, src, start, dur in jobs:
    x, sr = sf.read(src, dtype="float32", always_2d=True)
    if start is not None:
        a = int(start * sr)
        b = min(int((start + dur) * sr), len(x))
        x = x[a:b]
    # peak-normalise so loudness differences do not bias the comparison
    peak = float(np.abs(x).max())
    if peak > 0:
        x = x / peak * 0.89          # about -1 dBFS
    dst = os.path.join(OUT, name)
    sf.write(dst, x, sr)
    dur_s = len(x) / sr
    print("%-24s %6.1fs  %d Hz  %dch  %.1f MB" % (
        name, dur_s, sr, x.shape[1], os.path.getsize(dst) / 1048576))

# mp3 copies for easy sharing
import subprocess
for name, _, _, _ in jobs:
    wav = os.path.join(OUT, name)
    mp3 = wav[:-4] + ".mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                    "-b:a", "256k", mp3], check=False,
                   creationflags=0x08000000)
    if os.path.exists(mp3):
        print("%-24s %.1f MB" % (os.path.basename(mp3), os.path.getsize(mp3) / 1048576))

print("\n-> %s" % OUT)
