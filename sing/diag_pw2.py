"""验证：playwright 的 Edge 加上聚焦 + 点击后，loopback 能不能录到声音。"""
import array
import threading
import time
import wave
from pathlib import Path

import pyaudiowpatch as pa
from playwright.sync_api import sync_playwright

SING = Path(r"<PROJECT_ROOT>\sing")
OUT = SING / "source" / "devtest" / "pw_test.wav"
OUT.parent.mkdir(parents=True, exist_ok=True)
VID = "7534670384014495010"
res = {}


def rec(dur=8.0):
    p = pa.PyAudio()
    try:
        d = p.get_default_wasapi_loopback()
        ch, sr = int(d["maxInputChannels"]), int(d["defaultSampleRate"])
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
    finally:
        p.terminate()


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        channel="msedge", headless=False,
        args=["--autoplay-policy=no-user-gesture-required",
              "--disable-features=AudioServiceOutOfProcess",
              "--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto("https://www.douyin.com/video/%s" % VID,
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    page.bring_to_front()          # 拿到焦点
    try:
        page.mouse.click(640, 400)  # 一次真实点击，满足用户手势要求
        print("已点击页面", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("点击失败:", exc, flush=True)
    time.sleep(1.5)

    st = page.evaluate("""() => {
        const v = document.querySelector('video');
        return v ? {p: v.paused, t: v.currentTime, m: v.muted, vol: v.volume} : null;
    }""")
    print("播放状态:", st, flush=True)

    t = threading.Thread(target=rec, kwargs={"dur": 8.0})
    t.start()
    time.sleep(8.5)
    t.join()
    print("峰值 =", res.get("peak"), flush=True)
    browser.close()
