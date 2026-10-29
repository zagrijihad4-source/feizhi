"""让 Edge 播抖音视频，同时把 5 个 loopback 设备各录一遍，看声音落在哪。"""
import array
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyaudiowpatch as pa
from playwright.sync_api import sync_playwright

SING = Path(r"<PROJECT_ROOT>\sing")
OUT = SING / "source" / "devtest"
OUT.mkdir(parents=True, exist_ok=True)
VID = "7534670384014495010"
SECS = 6.0


def record(idx: int, name: str, path: Path) -> tuple[str, int]:
    p = pa.PyAudio()
    try:
        info = p.get_device_info_by_index(idx)
        ch = int(info["maxInputChannels"])
        sr = int(info["defaultSampleRate"])
        stream = p.open(format=pa.paInt16, channels=ch, rate=sr, input=True,
                        input_device_index=idx, frames_per_buffer=1024)
        frames, peak = [], 0
        for i in range(int(sr / 1024 * SECS)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            if i % 10 == 0:
                a = array.array("h")
                a.frombytes(data)
                if a:
                    peak = max(peak, max(abs(x) for x in a))
        stream.stop_stream()
        stream.close()
        with wave.open(str(path), "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"".join(frames))
        return name, peak
    finally:
        p.terminate()


p = pa.PyAudio()
devs = [(d["index"], d["name"]) for d in p.get_loopback_device_info_generator()]
p.terminate()
print("要测的设备:", [(i, n) for i, n in devs], flush=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=False,
                                 args=["--autoplay-policy=no-user-gesture-required"])
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto("https://www.douyin.com/video/%s" % VID,
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    st = page.evaluate("""() => {
        const v = document.querySelector('video');
        return v ? {p: v.paused, t: v.currentTime, m: v.muted, vol: v.volume} : null;
    }""")
    print("播放状态:", st, flush=True)

    with ThreadPoolExecutor(max_workers=len(devs)) as ex:
        futs = [ex.submit(record, i, n, OUT / ("dev_%d.wav" % i)) for i, n in devs]
        results = [f.result() for f in futs]

    print("\n=== 各设备峰值 ===")
    for name, peak in sorted(results, key=lambda r: -r[1]):
        print("  %-46s %d" % (name, peak))
    browser.close()
