"""不传 instructions 会怎样。

用户网页端只输入「你好呀宝贝，我真的超级喜欢你哦。」这一句，没填任何指令，
效果却是他要的。而我一直在传 100+ 字的第三人称导演指令。
这一轮直接对照：空 instructions vs 我的复杂指令，用他给的那句原文。
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
USER_TEXT = "你好呀宝贝，我真的超级喜欢你哦。"
CHARS = len(USER_TEXT.rstrip("。").replace("，", ""))

WARM = voice.style_for("温柔")

CASES = [
    ("X1-无指令-g1", USER_TEXT, None, 1.0),
    ("X2-无指令-g5", USER_TEXT, None, 5.0),
    ("X3-温柔指令-g5", USER_TEXT, WARM, 5.0),
    ("X4-无指令-g1-长文本", "你终于回来啦！我等你好久了，刚才一直盯着手机看，你再不回我都要睡着了。", None, 1.0),
]

for name, text, instr, g in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=g)
    (OUT / (name + ".wav")).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_x_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-22s %5.0f KB  指令=%s guidance=%s"
          % (name, len(wav) / 1024.0, "无" if not instr else "%d字" % len(instr), g))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("X[1234]-*.wav")):
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
    print("%-22s %5.2fs 最长浊音=%4.2fs F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, best*0.01, f0v.mean(), f0v.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
