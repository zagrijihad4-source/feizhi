"""分析 loopback 录音：找有声音的区间，转 24k 单声道，并做人声分离。"""
import array
import math
import subprocess
import sys
import wave
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
SRC = SING / "source" / "rec_raw.wav"
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")

with wave.open(str(SRC)) as w:
    n, sr, ch = w.getnframes(), w.getframerate(), w.getnchannels()
    raw = w.readframes(n)
print("录音 %.2fs  %dHz  %d 声道" % (n / sr, sr, ch))

a = array.array("h")
a.frombytes(raw[: (len(raw) // 2) * 2])
if ch == 2:
    a = array.array("h", [(a[i] + a[i + 1]) // 2 for i in range(0, len(a) - 1, 2)])
n = len(a)

win = int(sr * 1.0)
print("\n每秒能量：")
loud = []
for i in range(0, n - win, win):
    seg = a[i:i + win]
    rms = math.sqrt(sum(x * x for x in seg) / len(seg))
    t = i / sr
    bar = "#" * int(min(40, rms / 60))
    print("  %4.0fs  %6.0f  %s" % (t, rms, bar))
    if rms > 500:
        loud.append(t)

if not loud:
    print("\n没找到明显有声段")
    sys.exit(1)

start = max(0.0, min(loud) - 0.5)
end = min(n / sr, max(loud) + 1.5)
print("\n有声区间: %.1fs ~ %.1fs (%.1fs)" % (start, end, end - start))

clip = SRC.with_name("rec_clip.wav")
subprocess.run([FFMPEG, "-y", "-ss", str(start), "-t", str(end - start), "-i", str(SRC),
                "-ar", "24000", "-ac", "1", str(clip)], check=True, capture_output=True)
print("切出:", clip, "%.2f MB" % (clip.stat().st_size / 1048576))
