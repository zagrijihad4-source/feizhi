"""guidance 3 下重新生成温柔与开心，多次采样看音高稳定性，并发送。

单次采样波动太大（同一句无指令文本测出 205/246/250），
所以每档取 3 次，报中位数，避免拿一次结果当结论。
"""
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你今天几点睡的呀，我看你都困成这样了。"
VID = (tts.load_config().get("breeze") or {}).get("voice_id")
print("voice:", VID, " guidance:", (tts.load_config().get("breeze") or {}).get("guidance_scale"))

# 基准：无指令 3 次取中位
bases = []
for i in range(3):
    w = tts._breeze_synthesize(TEXT, None, VID, None, 90)
    p = OUT / ("H0-base%d.wav" % i)
    p.write_bytes(w)
    bases.append(p)

made = {}
for mood in ("温柔", "开心"):
    st = voice.style_for(mood)
    for i in range(3):
        w = tts._breeze_synthesize(TEXT, st, VID, None, 90)
        p = OUT / ("H0-%s-%d.wav" % (mood, i))
        p.write_bytes(w)
        made.setdefault(mood, []).append(p)
        if i == 0:   # 只发第一次给用户听
            pcm = ROOT / "tmp" / ("_h0_%s.pcm" % mood)
            tts.to_wechat_pcm(w, pcm)
            made[mood + "_pcm"] = pcm
    print("%s 生成 3 条" % mood)

A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
d = Path(r"C:\Users\api62\Desktop\语音诊断")

def f0_of(p):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; f0v = f0[f0 > 0]
    return len(x)/sr, f0v.mean(), f0v.std()

base = [f0_of(p) for p in sorted(d.glob("H0-base*.wav"))]
bmed = sorted(b[1] for b in base)[1]
print("基准 F0 三次: %s  中位 %.1f" % ([round(b[1],1) for b in base], bmed))
for mood in ("温柔", "开心"):
    vals = [f0_of(p) for p in sorted(d.glob("H0-%s-*.wav" % mood))]
    med = sorted(v[1] for v in vals)[1]
    dev = (med - bmed) / bmed * 100
    flag = "  <== 音色跑掉" if abs(dev) > 12 else ""
    print("%-4s F0 三次: %-26s 中位 %6.1f 偏离=%+5.1f%%%s"
          % (mood, str([round(v[1],1) for v in vals]), med, dev, flag))
'''
r = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)

import time  # noqa: E402
import bridge  # noqa: E402
b = bridge.HookBridge()
b.send_text("<WXID_FRIEND_A>",
            "guidance 从 8 降到 3 了（8 会把音高抬到失真），这两条是温柔和开心。")
time.sleep(2.5)
sender = voice.VoiceSender()
for mood in ("温柔", "开心"):
    pcm = made.get(mood + "_pcm")
    if pcm and pcm.exists():
        sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
        print("发送 %s: %.1fs sent=%s" % (mood, pcm.stat().st_size / 32000.0, sent))
        time.sleep(1.6)
