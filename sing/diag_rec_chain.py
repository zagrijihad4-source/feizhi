"""验证录音链路：用 ffplay 播一段已知音频，同时 loopback 录，看能不能录到。"""
import array
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import pyaudiowpatch as pa

FFPLAY = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffplay.exe")
SRC = Path(r"<PROJECT_ROOT>\sing\source\taoxi.wav")
OUT = Path(r"<PROJECT_ROOT>\sing\source\devtest\ffplay_test.wav")
OUT.parent.mkdir(parents=True, exist_ok=True)

res = {}


def rec(idx=None, dur=6.0):
    p = pa.PyAudio()
    try:
        d = (p.get_device_info_by_index(idx) if idx is not None
             else p.get_default_wasapi_loopback())
        ch, sr = int(d["maxInputChannels"]), int(d["defaultSampleRate"])
        name = d["name"]
        s = p.open(format=pa.paInt16, channels=ch, rate=sr, input=True,
                   input_device_index=d["index"], frames_per_buffer=1024)
        frames, peak = [], 0
        for i in range(int(sr / 1024 * dur)):
            data = s.read(1024, exception_on_overflow=False)
            frames.append(data)
            if i % 10 == 0:
                a = array.array("h")
                a.frombytes(data)
                if a:
                    peak = max(peak, max(abs(x) for x in a))
        s.stop_stream()
        s.close()
        with wave.open(str(OUT), "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"".join(frames))
        res["peak"] = peak
        res["name"] = name
        res["sr"] = sr
    finally:
        p.terminate()


t = threading.Thread(target=rec, kwargs={"dur": 6.0})
t.start()
time.sleep(0.5)
proc = subprocess.Popen([FFPLAY, "-nodisp", "-autoexit", "-loglevel", "quiet", str(SRC)])
time.sleep(5)
proc.terminate()
t.join()
print("设备:", res.get("name"), "sr:", res.get("sr"))
print("峰值 =", res.get("peak"))
print("录音文件:", OUT, "%.2f MB" % (OUT.stat().st_size / 1048576))
