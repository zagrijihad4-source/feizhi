"""Mix the SoulX-Singer cover and export deliverables.

Input : outputs/soulx/taoxi_full_soulx.wav (24 kHz mono vocal)
        source/taoxi_inst.wav               (44.1 kHz mono instrumental)
Output: desktop wav/mp3 + 16 kHz mono PCM slices for the WeChat voice hook.
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAL = os.path.join(HERE, "outputs", "soulx", "taoxi_full_soulx.wav")
INST = os.path.join(HERE, "source", "taoxi_inst.wav")
OUT = r"C:\Users\api62\Desktop\绯栀对比"
SR = 44100
SLICE_SEC = 42.0          # WeChat voice clips cap at 60 s; leave encode headroom
INST_GAIN = 0.42
VOCAL_GAIN = 1.0
PEAK = 0.89


def load_mono(path, sr):
    y, s = sf.read(path, dtype="float64", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if s != sr:
        from math import gcd
        g = gcd(int(s), int(sr))
        y = resample_poly(y, sr // g, s // g)
    return y


def main():
    os.makedirs(OUT, exist_ok=True)
    voc = load_mono(VOCAL, SR)
    inst = load_mono(INST, SR)
    n = min(len(voc), len(inst))
    voc, inst = voc[:n], inst[:n]
    print(f"vocal {len(voc) / SR:.2f}s  inst {len(inst) / SR:.2f}s  sr={SR}")

    # match loudness of the two stems on their active parts before mixing
    a = voc / (np.sqrt(np.mean(voc ** 2)) + 1e-9)
    b = inst / (np.sqrt(np.mean(inst ** 2)) + 1e-9)
    mix = VOCAL_GAIN * a + INST_GAIN * b
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * PEAK

    dry = voc / (np.max(np.abs(voc)) + 1e-9) * PEAK
    wav_path = os.path.join(OUT, "04-绯栀-SoulX-潮汐-全曲.wav")
    dry_path = os.path.join(OUT, "04-绯栀-SoulX-潮汐-纯人声.wav")
    sf.write(wav_path, mix.astype("float32"), SR)
    sf.write(dry_path, dry.astype("float32"), SR)
    print("wav :", wav_path)
    print("dry :", dry_path)

    # 16 kHz mono s16le slices for the WeChat voice hook (anti-aliased)
    pcm_dir = os.path.join(HERE, "outputs", "soulx", "pcm")
    os.makedirs(pcm_dir, exist_ok=True)
    step = int(SLICE_SEC * SR)
    idx = 0
    for start in range(0, len(mix), step):
        seg = mix[start:start + step]
        if len(seg) < SR * 3:
            break
        pcm = resample_poly(seg, 16000, SR)
        pcm16 = np.clip(pcm * 32767.0, -32768, 32767).astype("<i2")
        p = os.path.join(pcm_dir, f"slice{idx}.pcm")
        pcm16.tofile(p)
        print(f"pcm  {p}  {len(pcm16) / 16000:.1f}s")
        idx += 1


if __name__ == "__main__":
    main()
