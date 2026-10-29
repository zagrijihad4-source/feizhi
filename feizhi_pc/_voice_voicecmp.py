"""最后的变量：克隆音色 vs 预设音色。

用户说网页端效果好、且认可克隆音色（"音色没问题"）。但"音色像"和"会演"是两件事：
克隆样本 feizhi_B_sample.wav 是 voicedesign 生成的"冷清慵懒"，F0 sd 只有 55.2，
voiceclone 会把韵律也往样本上拉 —— 表达力可能被样本锁死。

同一个句子、同样不传指令，只换音色。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你好呀宝贝，我真的超级喜欢你哦。"

VOICES = [
    ("克隆-绯栀", "voc_uj5qvdgfhuhz"),
    ("Deema", "voc_9k38qhkc6qrm"),
    ("Raina", "voc_n9rbmmr8uawn"),
    ("Annie", "voc_dv7rfyk47773"),
]

for name, vid in VOICES:
    try:
        wav = tts._breeze_synthesize(TEXT, None, vid, None, 90)
    except Exception as e:  # noqa: BLE001
        print("%-12s 失败 %r" % (name, e))
        continue
    (OUT / ("Y-%s.wav" % name)).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_y_%s.pcm" % name)
    tts.to_wechat_pcm(wav, pcm)
    print("%-12s %5.0f KB" % (name, len(wav) / 1024.0))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("Y-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    best = cur = 0
    for v in voiced:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-12s %5.2fs 最长浊音=%4.2fs F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem.replace("Y-",""), dur, best*0.01, f0v.mean(), f0v.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
