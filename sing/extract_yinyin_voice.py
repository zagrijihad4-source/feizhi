"""从录屏音频里提取音音子的清唱（切段 + 人声分离）。"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SING = Path(r"<PROJECT_ROOT>\sing")
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else SING / "source" / "rec_raw2.wav"
CLIP = SING / "source" / "yinyin_clip.wav"
OUT_WAV = SING / "source" / (sys.argv[2] if len(sys.argv) > 2 else "yinyin_vocal.wav")
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")
ROOT = SING / "pretrained_models" / "SoulX-Singer-Preprocess"

sys.path.insert(0, str(SING / "SoulX-Singer"))

# 1) 已是 24k 单声道就直接用，否则转
subprocess.run([FFMPEG, "-y", "-i", str(SRC),
                "-ar", "24000", "-ac", "1", str(CLIP)], check=True, capture_output=True)
print("预处理:", CLIP, "%.2f MB" % (CLIP.stat().st_size / 1048576), flush=True)

# 2) 人声分离
from preprocess.tools.vocal_separation.model import VocalSeparator  # noqa: E402

t0 = time.time()
sep = VocalSeparator(
    sep_model_path=str(ROOT / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
    sep_config_path=str(ROOT / "mel-band-roformer-karaoke" / "config_karaoke_becruily.yaml"),
    der_model_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"),
    der_config_path=str(ROOT / "dereverb_mel_band_roformer" / "dereverb_mel_band_roformer_anvuew.yaml"),
    device="cuda", use_der=False, verbose=False,
)
print("模型加载 %.1fs" % (time.time() - t0), flush=True)

t1 = time.time()
out = sep.process(str(CLIP))
voc = np.asarray(out.vocals)
if voc.ndim > 1:
    voc = voc.mean(axis=0) if voc.shape[0] < voc.shape[-1] else voc.mean(axis=-1)
sr = int(out.sample_rate)
print("分离 %.1fs  sr=%d  samples=%d" % (time.time() - t1, sr, len(voc)), flush=True)

# 重采样到 24k（模型要求）
if sr != 24000:
    import librosa
    voc = librosa.resample(voc.astype(np.float32), orig_sr=sr, target_sr=24000)
    sr = 24000

outp = OUT_WAV
sf.write(str(outp), voc, sr)
print("输出:", outp, "%.2f MB  %.2fs" % (
    outp.stat().st_size / 1048576, len(voc) / sr))
