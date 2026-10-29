"""把 batch 目录下 19 条录屏音频，各截最饱满的 10 秒，拼成一条，做一次人声分离。"""
import array
import math
import subprocess
import sys
import wave
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
BATCH = SING / "source" / "batch"
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")
SEG = 10.0

recs = sorted(BATCH.glob("yy_*.wav"))
print("找到 %d 条录音" % len(recs))
parts = []
for p in recs:
    with wave.open(str(p)) as w:
        n, sr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    a = array.array("h")
    a.frombytes(raw[: (len(raw) // 2) * 2])
    if ch == 2:
        a = array.array("h", [(a[i] + a[i + 1]) // 2 for i in range(0, len(a) - 1, 2)])
    n = len(a)
    win = int(sr * 0.5)
    need = int(SEG / 0.5)
    best = (0.0, 0)
    for s in range(0, max(1, n // win - need + 1)):
        seg = a[s * win: min(n, s * win + int(SEG * sr))]
        if not seg:
            continue
        rms = math.sqrt(sum(x * x for x in seg) / len(seg))
        if rms > best[0]:
            best = (rms, s * win)
    if best[0] < 300:
        print("  %-12s 峰值 %.0f 太低，跳过" % (p.name, best[0]))
        continue
    out = BATCH / ("cut_" + p.name)
    subprocess.run([FFMPEG, "-y", "-ss", str(best[1] / sr), "-t", str(SEG), "-i", str(p),
                    "-ar", "24000", "-ac", "1", str(out)], check=True, capture_output=True)
    print("  %-12s 取 %.0fs 起 RMS %.0f" % (p.name, best[1] / sr, best[0]))
    parts.append(out)

if not parts:
    raise SystemExit("没有可用片段")
lst = BATCH / "concat_all.txt"
lst.write_text("\n".join("file '%s'" % p.as_posix() for p in parts), encoding="utf-8")
merged = SING / "source" / "yinyin_all.wav"
subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-ar", "24000", "-ac", "1", str(merged)], check=True, capture_output=True)
with wave.open(str(merged)) as w:
    dur = w.getnframes() / w.getframerate()
print("\n合并 %d 段 -> %s  %.1f MB  %.1fs" % (
    len(parts), merged.name, merged.stat().st_size / 1048576, dur))
