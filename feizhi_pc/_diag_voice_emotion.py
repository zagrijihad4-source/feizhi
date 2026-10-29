"""诊断语音「没有感情色彩」的根因。

查两件事：
  1. voiceclone 的克隆样本 `feizhi_B_sample.wav` 到底是「说话」还是「唱」；
  2. 实际发出去那条 TTS 的 F0/能量动态，和样本比差多少。

判据（情感色彩的可计算代理）：
  * F0 标准差 / 范围：说话有语调起伏，唱歌是稳定旋律，长音多 → 标准差形态不同
  * 能量动态（dB p95-p5）：有表情的语音动态大
  * 静音比例：说话有换气停顿，唱歌（尤其中间段）少
  * F0 连续同值占比：唱歌长音会让大量帧落在同一音高附近
"""
import sys
import wave
from pathlib import Path

import numpy as np
import parselmouth
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE = Path(r"<PROJECT_ROOT>\feizhi_pc\voice\feizhi_B_sample.wav")
PCM = Path(r"<PROJECT_ROOT>\tmp\tts_11af913ab0c92bee.pcm")


def read_pcm16(path):
    b = path.read_bytes()
    x = np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0
    return x, 16000


def stats(x, sr, label):
    x = np.asarray(x, dtype=np.float64)
    dur = len(x) / sr
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    # 能量
    frame = max(1, int(sr * 0.02))
    n = len(x) // frame
    rms = np.array([np.sqrt(np.mean(x[i * frame:(i + 1) * frame] ** 2) + 1e-12)
                    for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    dyn = float(np.percentile(loud, 95) - np.percentile(loud, 5)) if len(loud) > 4 else 0.0
    silent = float(np.mean(db < db.max() - 35))

    # F0 是否大量堆在同一音高（长音/旋律特征）
    if len(f0) > 10:
        hist, _ = np.histogram(f0, bins=np.arange(75, 605, 10))
        top_share = float(hist.max() / hist.sum())
    else:
        top_share = 0.0

    print("%-14s dur=%5.2fs  F0 mean=%5.1f Hz  sd=%5.1f  range=%5.1f~%5.1f"
          % (label, dur, f0.mean() if len(f0) else 0,
             f0.std() if len(f0) else 0,
             f0.min() if len(f0) else 0, f0.max() if len(f0) else 0))
    print("%-14s 动态=%5.1f dB  静音占比=%.1f%%  F0峰值集中度=%.2f"
          % ("", dyn, silent * 100, top_share))
    return dur


print("=== 克隆样本 ===")
x, sr = sf.read(str(SAMPLE), dtype="float32", always_2d=True)
x = x.mean(axis=1)
stats(x, sr, "B_sample")

print()
print("=== 实际发出去的 TTS（mimo voiceclone 输出）===")
if PCM.exists():
    y, ysr = read_pcm16(PCM)
    stats(y, ysr, "tts output")
else:
    print("PCM 不存在：%s" % PCM)
