"""录系统声音（WASAPI loopback），用于抓取浏览器里播放的抖音视频音频。"""
import sys
import time
import wave
from pathlib import Path

import pyaudiowpatch as pa

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    r"<PROJECT_ROOT>\sing\source\rec_raw.wav")

p = pa.PyAudio()
try:
    dev = p.get_default_wasapi_loopback()
except Exception as exc:  # noqa: BLE001
    raise SystemExit("拿不到 loopback 设备: %s" % exc)

ch = int(dev["maxInputChannels"])
sr = int(dev["defaultSampleRate"])
print("设备:", dev["name"], " 声道", ch, " 采样率", sr, " 录制 %.0fs" % DUR, flush=True)

stream = p.open(format=pa.paInt16, channels=ch, rate=sr, input=True,
                input_device_index=dev["index"], frames_per_buffer=1024)

frames = []
chunk = 1024
total = int(sr / chunk * DUR)
peak = 0
t0 = time.time()
for i in range(total):
    data = stream.read(chunk, exception_on_overflow=False)
    frames.append(data)
    # 粗算峰值，判断有没有真的录到声音
    if i % 20 == 0:
        import array
        a = array.array("h")
        a.frombytes(data)
        if a:
            peak = max(peak, max(abs(x) for x in a))
stream.stop_stream()
stream.close()
p.terminate()

OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(ch)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(b"".join(frames))

n = OUT.stat().st_size
print("写出 %s  %.2f MB  实际时长 %.2fs  峰值 %d" % (
    OUT, n / 1048576, (time.time() - t0), peak))
if peak < 200:
    print("警告：峰值很低，可能没录到声音（播放了吗？静音了吗？）")
