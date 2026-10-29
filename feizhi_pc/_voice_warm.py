"""对照：现用「温柔」档（克制配方） vs 外放的热情温柔。

诊断依据：现有 MOODS 的指导里堆着抑制词——
  「音量轻」「尾音轻轻下压」「不要煽情」（温柔档）
  「笑到一半收住」「气息比声音多」（我上一版）
这些词合起来就是冷淡的配方。要热情，必须反过来写：
音量正常、尾音上扬、笑出来不收、明确禁止矜持。
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
CHARS = 20

WARM_OLD = voice.style_for("温柔")      # 现用：克制

# 外放版：把抑制词全部换成外放词，并明确禁止克制
WARM_NEW = (
    "她刚听见他的声音，心里一下就热了，笑先出来再开口，声音是亮的、暖的。"
    "音量正常，不要压低；句尾往上轻轻带，不要往下沉；"
    "中间夹一声没忍住的笑，笑完接着往下说。"
    "整句连着说，语速轻快。不要矜持，不要克制的温柔 —— 就是高高兴兴跟他说话。"
)

CASES = [
    ("Q-现用温柔档", TEXT, WARM_OLD, None),
    ("R-外放热情", TEXT, WARM_NEW, None),
    ("S-外放热情-speed1.1", TEXT, WARM_NEW, 1.1),
]

for name, text, instr, sp in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, speed=sp)
    p = OUT / (name + ".wav")
    p.write_bytes(wav)
    pcm = ROOT / "tmp" / ("_vt3_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-22s %5.0f KB  指令 %d 字 speed=%s" % (name, len(wav) / 1024.0, len(instr), sp))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
CH = 20
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("[QRS]-*.wav")):
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
    print("%-22s %5.2fs %4.2f字/秒 F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, CH/dur, f0.mean(), f0.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
