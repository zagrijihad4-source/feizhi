"""把多次录屏里最有声的片段拼成一条长音色参考，再一次性做人声分离。"""
import array
import math
import subprocess
import sys
import wave
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
SRC = SING / "source"
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")

RECS = ["rec_raw2.wav", "yy2.wav", "yy3.wav", "yy4.wav", "yy5.wav"]
SEG = 15.0          # 每条取多少秒
parts = []

for name in RECS:
    p = SRC / name
    if not p.exists():
        print("跳过（不存在）", name)
        continue
    with wave.open(str(p)) as w:
        n, sr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    a = array.array("h")
    a.frombytes(raw[: (len(raw) // 2) * 2])
    if ch == 2:
        a = array.array("h", [(a[i] + a[i + 1]) // 2 for i in range(0, len(a) - 1, 2)])
    n = len(a)
    win = int(sr * 0.5)
    # 找能量最高的连续 SEG 秒
    need = int(SEG / 0.5)
    best = (0.0, 0)
    for s in range(0, max(1, n // win - need + 1)):
        seg_s = s * win
        seg_e = min(n, seg_s + int(SEG * sr))
        seg = a[seg_s:seg_e]
        if not seg:
            continue
        rms = math.sqrt(sum(x * x for x in seg) / len(seg))
        if rms > best[0]:
            best = (rms, seg_s)
    if best[0] < 300:
        print("%-14s 峰值 RMS %.0f 太低，跳过" % (name, best[0]))
        continue
    st = best[1] / sr
    out = SRC / ("cut_" + name)
    subprocess.run([FFMPEG, "-y", "-ss", str(st), "-t", str(SEG), "-i", str(p),
                    "-ar", "24000", "-ac", "1", str(out)], check=True, capture_output=True)
    print("%-14s 取 %.1fs 起 %.0fs  RMS %.0f -> %s" % (
        name, SEG, st, best[0], out.name))
    parts.append(out)

if not parts:
    raise SystemExit("没有可用片段")

# 拼接
lst = SRC / "concat.txt"
lst.write_text("\n".join("file '%s'" % p.as_posix() for p in parts), encoding="utf-8")
merged = SRC / "yinyin_voice_long.wav"
subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-ar", "24000", "-ac", "1", str(merged)], check=True, capture_output=True)
with wave.open(str(merged)) as w:
    dur = w.getnframes() / w.getframerate()
print("\n合并: %s  %.1f MB  %.1fs（%d 段）" % (
    merged.name, merged.stat().st_size / 1048576, dur, len(parts)))
