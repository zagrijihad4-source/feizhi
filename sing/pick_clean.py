"""分析绯栀音色样本，按 0.5 秒窗口算能量，找最干净、最连续的 8 秒片段。"""
import array
import math
import sys
import wave
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\feizhi_pc\voice\feizhi_B_sample.wav")
OUT = Path(r"<PROJECT_ROOT>\sing\source\feizhi_clean8s.wav")

with wave.open(str(SRC)) as w:
    n = w.getnframes()
    sr = w.getframerate()
    ch = w.getnchannels()
    sw = w.getsampwidth()
    raw = w.readframes(n)
print("源: %.2fs  %dHz  %d 声道  %d bit" % (n / sr, sr, ch, sw * 8))

a = array.array("h")
a.frombytes(raw[: (len(raw) // 2) * 2])
if ch == 2:
    a = array.array("h", [a[i] for i in range(0, len(a), 2)])
    ch = 1
n = len(a)

win = int(sr * 0.5)          # 0.5 秒窗
frames = []
for i in range(0, n - win, win):
    seg = a[i:i + win]
    ms = sum(x * x for x in seg) / len(seg)
    rms = math.sqrt(ms)
    # 过零率粗估：静音段很低，噪声段很高
    zc = sum(1 for k in range(1, len(seg)) if (seg[k - 1] < 0) != (seg[k] < 0))
    frames.append((i / sr, rms, zc / win))

rms_all = [f[1] for f in frames]
mx = max(rms_all) or 1
print("\n窗口数 %d（每 0.5s）  RMS 最大 %.0f" % (len(frames), mx))
print("时间轴（rms 归一化 / 过零率）:")
for t, rms, zc in frames:
    bar = "#" * int(rms / mx * 40)
    flag = ""
    if rms < mx * 0.12:
        flag = "  <-弱"
    if zc > 0.25:
        flag += "  <-噪声?"
    print("  %5.1fs  %5.0f  %.2f  %s%s" % (t, rms, zc, bar, flag))

# 找能量最高且连续 8 秒（16 个窗）的起点
need = 16   # 8 秒 / 0.5 秒每窗
best = None
for s in range(0, len(frames) - need + 1):
    seg = frames[s:s + need]
    score = sum(f[1] for f in seg) / need
    # 惩罚：段内过弱的窗口
    weak = sum(1 for f in seg if f[1] < mx * 0.15)
    score *= (1.0 - weak / need * 0.9)
    if best is None or score > best[0]:
        best = (score, seg[0][0], seg[-1][0] + 0.5, weak)
print("\n最佳 8 秒: %.1fs ~ %.1fs  平均RMS %.0f  弱窗 %d" % (best[1], best[2], best[0], best[3]))

start = int(best[1] * sr)
end = min(n, start + int(8.0 * sr))
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(a[start:end].tobytes())
print("已写出 %s  %.2fs" % (OUT, (end - start) / sr))
