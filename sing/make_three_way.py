"""Build the three-way comparison the user asked for, all on 潮汐:

  1. original singer  — taoxi.wav (with instrumental), same 45s window
  2. model speaking   — TTS line, then pushed through yinyin.pth (no singing)
  3. model singing    — the converted 潮汐, same 45s window

Each becomes a separate 16k PCM ready to send as a WeChat voice message.
"""
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

SING = r"<PROJECT_ROOT>\sing"
FEIZHI = r"<PROJECT_ROOT>\feizhi_pc"
sys.path.insert(0, FEIZHI)
sys.path.insert(0, SING)

START = 83
DUR = 45
OUT = os.path.join(SING, "outputs", "rvc")
os.makedirs(OUT, exist_ok=True)

SPOKEN = ("嗯，我在的。这首歌叫潮汐，我唱过一遍给你听了。"
          "现在我用说的，你自己听听，这声音是不是同一个人。")


def to_pcm(wav_path, out_path, start=None, dur=None):
    """Resample a wav to 16k mono s16le; optionally cut a window first."""
    x, sr = sf.read(wav_path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if start is not None:
        a = int(start * sr)
        b = min(int((start + dur) * sr), len(x))
        x = x[a:b]
    n = int(round(len(x) * 16000 / sr))
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    y = y / max(float(np.abs(y).max()), 1e-9) * 0.92
    open(out_path, "wb").write((y * 32767).astype("<i2").tobytes())
    print("  -> %s  %.1fs" % (os.path.basename(out_path), len(y) / 16000))


print("[1/3] 原唱")
orig_wav = os.path.join(SING, "source", "taoxi.wav")
to_pcm(orig_wav, os.path.join(OUT, "cmp1_original.pcm"), START, DUR)

print("[2/3] 模型说话（TTS -> yinyin.pth）")
import tts  # noqa: E402

pcm_path = tts.synthesize_pcm(SPOKEN, style="平静地、像在跟人说话")
raw = np.fromfile(str(pcm_path), dtype="<i2").astype(np.float32) / 32768.0
spoken_wav = os.path.join(OUT, "cmp2_spoken_src.wav")
sf.write(spoken_wav, raw, 16000)
print("  tts %.1fs" % (len(raw) / 16000))

env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
py = os.path.join(SING, ".venv", "Scripts", "python.exe")
spoken_conv = os.path.join(OUT, "cmp2_spoken_yinyin.wav")
r = subprocess.run([py, "-u", os.path.join(SING, "rvc_cover.py"), spoken_wav, spoken_conv,
                    "--model", "yinyin.pth", "--index-rate", "0", "--protect", "0.5"],
                   cwd=SING, env=env, capture_output=True, text=True,
                   encoding="utf-8", errors="ignore", timeout=600,
                   creationflags=0x08000000)
print("  rvc rc=%s" % r.returncode)
if not os.path.exists(spoken_conv):
    print("  FAILED:", (r.stdout or "")[-400:], (r.stderr or "")[-300:])
    sys.exit(1)
to_pcm(spoken_conv, os.path.join(OUT, "cmp2_spoken.pcm"))

print("[3/3] 模型唱歌")
sing_wav = os.path.join(OUT, "taoxi_hi_mix.wav")
to_pcm(sing_wav, os.path.join(OUT, "cmp3_singing.pcm"), START, DUR)

print("\ndone")
