"""mimo vs breeze：同一文本、同一克隆样本、同一套 style。

不动 tts_config.json，用 monkey-patch 临时把 provider 指到 mimo。
文本故意带一个 [轻笑]，看两个模型对音频标签的处理差异
（mimo 也支持方括号标签，但语义可能不同）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你回来啦，我等你好久了，[轻笑] 今天累不累呀。"
STYLE = voice.style_for("温柔")

# —— breeze ——
wav_b = tts._breeze_synthesize(TEXT, STYLE, None, None, 90)
(OUT / "T-breeze-温柔.wav").write_bytes(wav_b)
print("breeze  %5.0f KB" % (len(wav_b) / 1024.0))

# —— mimo（临时切 provider）——
orig = tts.load_config


def forced_mimo():
    c = dict(orig())
    c["provider"] = "mimo"
    return c


tts.load_config = forced_mimo
try:
    wav_m = tts.synthesize_wav(TEXT, style=STYLE)
finally:
    tts.load_config = orig
(OUT / "T-mimo-温柔.wav").write_bytes(wav_m)
print("mimo    %5.0f KB" % (len(wav_m) / 1024.0))

for name in ("T-breeze-温柔", "T-mimo-温柔"):
    wav = (OUT / (name + ".wav")).read_bytes()
    pcm = ROOT / "tmp" / ("_cmp_%s.pcm" % name.split("-")[1])
    tts.to_wechat_pcm(wav, pcm)
    print("pcm %-16s %.1f 秒" % (pcm.name, pcm.stat().st_size / 32000.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
CH = 20
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("T-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; f0 = f0[f0 > 0]
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-16s %5.2fs %4.2f字/秒 F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, CH/dur, f0.mean(), f0.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
