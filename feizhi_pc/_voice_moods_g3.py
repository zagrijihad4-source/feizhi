# -*- coding: utf-8 -*-
r"""guidance_scale=3 下九档 mood 全量复验。

为什么这么设计：
  ★ 昨晚最大的教训是 **F0 标准差是假指标**。我整晚追着高 sd 当"有情绪"，
    而你挑出来的「最自然」那条（DD-真音-唱歌克隆.wav）sd 恰恰最低（37.9）、
    帧间跳也最低（4.0）。真正的"自然"= 音高贴近 base + 帧与帧之间不跳。
    所以这次主指标换成：**相对 base 的音高偏移 %** 和 **帧间跳**。

  ★ 第二个教训是**单次测量不可信**：同一套参数三次跑出 F0 205.3 / 246.2 / 250.4，
    温柔 sd 一次 37.9 一次 76.2。所以每档跑 3 个样本取中位数。

  ★ 第三：base（不发 instructions，只给文本）必须一起测，否则"偏移"没有参照。

产物：C:\Users\api62\Desktop\语音诊断\J1-<mood>-<n>.wav
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts      # noqa: E402
import voice    # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
VENV = r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe"
# 21 字，昨晚用来量时长的同一句，方便和旧数据对比
TEXT = "你今天几点睡的呀，我看你都困成这样了。"
N = 3

cfg = tts.load_config()
bz = cfg.get("breeze") or {}
VID = bz.get("voice_id")
print("voice_id = %s  guidance = %s  speed = %s"
      % (VID, bz.get("guidance_scale"), bz.get("speed")))
print("文本 %d 字：%s" % (len(TEXT), TEXT))
print("每档 %d 个样本，共 %d 次合成\n" % (N, (len(voice.MOODS) + 1) * N))

OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("J1-*.wav"):
    old.unlink()

plan = [("BASE", None)] + [(m, voice.style_for(m)) for m in voice.MOODS]
made = 0
for name, style in plan:
    for i in range(N):
        try:
            wav = tts._breeze_synthesize(TEXT, style, VID, None, 120)
        except Exception as exc:  # noqa: BLE001
            print("  %s #%d 合成失败: %r" % (name, i + 1, exc))
            continue
        (OUT / ("J1-%s-%d.wav" % (name, i + 1))).write_bytes(wav)
        made += 1
    print("  %-4s 完成" % name, flush=True)

print("\n合成 %d 个文件，开始测量…\n" % made)

MEASURE = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

rows = {}
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("J1-*.wav")):
    parts = p.stem.split("-")          # J1-名称-序号
    name = parts[1]
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]
    voiced = f0 > 0
    f0v = f0[voiced]
    if len(f0v) < 20:
        continue
    # 帧间跳：相邻有声帧的音高差绝对值均值，越大越"抖"
    d = np.abs(np.diff(f0[voiced]))
    jump = float(np.mean(d)) if len(d) else 0.0
    half = len(f0v) // 2
    drift = float(abs(f0v[:half].mean() - f0v[half:].mean()))
    fr = max(1, int(sr * 0.02))
    n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    dyn = float(np.percentile(loud, 95) - np.percentile(loud, 5)) if len(loud) > 4 else 0.0
    sil = float(np.mean(db < db.max() - 35)) * 100
    rows.setdefault(name, []).append(
        dict(dur=dur, mean=float(f0v.mean()), sd=float(f0v.std()),
             jump=jump, drift=drift, dyn=dyn, sil=sil))

import statistics as stt
med = {k: {m: stt.median([r[m] for r in v]) for m in v[0]} for k, v in rows.items()}
base = med.get("BASE", {}).get("mean")

print("%-5s %6s %7s %7s %6s %6s %6s %6s" %
      ("档位", "时长", "F0", "vs base", "sd", "帧间跳", "动态", "静音"))
print("-" * 62)
order = ["BASE", "傲娇", "心虚", "委屈", "温柔", "慵懒", "开心", "强撑", "娇嗔", "害羞"]
for name in order:
    if name not in med:
        continue
    m = med[name]
    off = (m["mean"] - base) / base * 100 if base else 0.0
    print("%-5s %5.2fs %7.1f %+6.1f%% %6.1f %6.1f %6.1f %5.1f%%" %
          (name, m["dur"], m["mean"], off, m["sd"], m["jump"], m["dyn"], m["sil"]))

print()
if base:
    print("基准 F0 = %.1f Hz（无 instructions）" % base)
    bad = [n for n in order if n in med and n != "BASE"
           and abs((med[n]["mean"] - base) / base) > 0.15]
    print("音高偏移超 ±15%% 的档位: %s" % (", ".join(bad) or "无"))
    slow = [n for n in order if n in med and n != "BASE" and med[n]["dur"] > 7.0]
    print("时长超 7s 的档位: %s" % (", ".join(slow) or "无"))
    # 原始样本离散度：看单次测量到底有多不可靠
    for n in ("BASE", "温柔"):
        if n in rows and len(rows[n]) > 1:
            vals = [round(r["mean"], 1) for r in rows[n]]
            print("%s 三次 F0 原始值: %s" % (n, vals))
'''

r = subprocess.run([VENV, "-c", MEASURE], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print(r.stdout or r.stderr)
