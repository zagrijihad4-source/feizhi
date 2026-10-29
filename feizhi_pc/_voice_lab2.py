"""Breeze 语音第二版：换写法。

用户反馈「情绪太小、人机感过重、音色没问题，是写法的问题」。
对照官方示例的结构（情绪+强度 / 声音特征 / 具体情境 / 身体状态 / 节奏），
第一版那种「语气软、带点心疼、别念稿」全是抽象形容词，模型只能平铺地念。

这一版按示例的密度重写，并且：
  * 用 `[叹气]` `[轻笑]` 在文本里标出情绪落点；
  * 一次只调一个变量（指令强度 / guidance）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

TAG_TEXT = "你今天几点睡的呀，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。[轻笑]"
PLAIN_TEXT = "你今天几点睡的呀眼睛都睁不开了吧还嘴硬说没困"

# E：具体到声音动作，但不提"停顿"（怕触发插静音），改成"接得紧"
E = (
    "说的时候声音是软的、带黏，像刚靠过来贴着人说话。"
    "前半句带着埋怨，「几点睡的」往上挑一下；"
    "叹完气音量变小、气声变多，句子接得紧一点，别一句一顿；"
    "说到「还嘴硬」忍不住笑出来，笑到一半收住。"
    "不要念稿子，要像忍不住说出来的。"
)

# F：再加身体状态与情境，密度接近官方示例
F = (
    "她刚被吵醒，人还是软的，靠在他肩上说话，气息比声音多。"
    "埋怨他熬夜，但没有真生气；说到「还嘴硬」自己先笑了，笑得有点不好意思。"
    "整句连成一串说出来，不要一句一句断，也不要把每个字都咬清楚。"
)

CASES = [
    ("E-具体动作-g2", TAG_TEXT, E, 2.0),
    ("F-身体状态-g3", TAG_TEXT, F, 3.0),
    ("G-具体动作-无标点-g2", PLAIN_TEXT, E, 2.0),
]

made = []
for name, text, instr, g in CASES:
    wav = tts._breeze_synthesize(text, instr, None, None, 90, guidance=g)
    wav_path = OUT / ("N-%s.wav" % name)
    wav_path.write_bytes(wav)
    pcm = ROOT / "tmp" / ("_vt2_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    made.append((name, pcm))
    print("%-22s wav %5.0f KB  指令 %d 字  guidance=%s"
          % (name, len(wav) / 1024.0, len(instr), g))

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("N-*.wav")):
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
    print("%-24s %5.2fs F0=%6.1f sd=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, f0.mean(), f0.std(),
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
print("pcm:", [p.name for _, p in made])
