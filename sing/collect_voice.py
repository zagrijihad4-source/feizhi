"""全自动采集抖音作者的作品音频：playwright 驱动 Edge 播放 + loopback 录音。

用法:
    python collect_voice.py <sec_uid 或主页URL> [目标数量] [每个录多少秒]

要点（都是踩过的坑）：
  - 用 channel="msedge"，不用下 playwright 的 chromium
  - 视频页会自动播放，**不要发任何按键**（空格会暂停）
  - 导航后等 2.5 秒再开录，避开加载期的静音
  - 录音是系统 loopback，会真的出声
"""
import sys
import time
from pathlib import Path

import pyaudiowpatch as pa
import requests
from playwright.sync_api import sync_playwright

SING = Path(r"<PROJECT_ROOT>\sing")
OUT = SING / "source" / "batch"
OUT.mkdir(parents=True, exist_ok=True)

SEC_UID = ("MS4wLjABAAAAR1kx7Xkq66oz6ilu2f49kmDZ9bU36CO5Q3vNXkl274BIZ6Np_rZCDKgXVIr3teds")
HOME = "https://www.douyin.com/user/" + SEC_UID

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 26.0
SETTLE = 2.5


def record(path: Path, dur: float) -> int:
    """录 dur 秒系统输出，返回峰值。"""
    p = pa.PyAudio()
    try:
        dev = p.get_default_wasapi_loopback()
        ch = int(dev["maxInputChannels"])
        sr = int(dev["defaultSampleRate"])
        import array
        import wave
        stream = p.open(format=pa.paInt16, channels=ch, rate=sr, input=True,
                        input_device_index=dev["index"], frames_per_buffer=1024)
        frames = []
        peak = 0
        chunk = 1024
        for i in range(int(sr / chunk * dur)):
            data = stream.read(chunk, exception_on_overflow=False)
            frames.append(data)
            if i % 20 == 0:
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
        return peak
    finally:
        p.terminate()


def collect_ids(page, need: int) -> list[str]:
    """在主页反复滚动，收集 /video/ 链接里的 id。"""
    ids: list[str] = []
    seen = set()
    for round_ in range(12):
        hrefs = page.eval_on_selector_all(
            "ul li a[href*='/video/']", "els => els.map(e => e.getAttribute('href'))")
        for h in hrefs or []:
            if not h:
                continue
            vid = h.split("/video/")[-1].split("?")[0]
            if vid and vid not in seen:
                seen.add(vid)
                ids.append(vid)
        if len(ids) >= need:
            break
        page.mouse.wheel(0, 2500)
        time.sleep(1.5)
        print("  滚动第 %d 轮，已收集 %d 个" % (round_ + 1, len(ids)), flush=True)
    return ids[:need]


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=False,
                                     args=["--autoplay-policy=no-user-gesture-required",
                                           "--disable-features=AudioServiceOutOfProcess",
                                           "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        print("打开主页…", flush=True)
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        ids = collect_ids(page, TARGET)
        print("共 %d 个视频 ID" % len(ids), flush=True)

        ok = 0
        for i, vid in enumerate(ids):
            out = OUT / ("yy_%02d.wav" % i)
            if out.exists() and out.stat().st_size > 200000:
                print("[跳过] %s 已存在" % out.name, flush=True)
                ok += 1
                continue
            url = "https://www.douyin.com/video/%s" % vid
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:  # noqa: BLE001
                print("  导航失败 %s: %s" % (vid, exc), flush=True)
                continue
            # ★ 必须做的三步：等渲染 → 切前台 → 一次真实点击。
            #   不等渲染就点，点到的还是空白页，手势不成立；
            #   手势不成立时 video 元素显示 paused=False 在播，但系统一点声音都没有
            #   —— Chromium 要求「用户手势」之后才真正出声，症状就是峰值 0。
            time.sleep(3.0)
            try:
                page.bring_to_front()
                page.mouse.click(8, 8)      # 点页面边角，避开播放器控件
            except Exception:  # noqa: BLE001
                pass
            time.sleep(SETTLE)
            peak = record(out, SECS)
            flag = "OK " if peak > 500 else "弱!"
            print("[%s] %s -> %s  峰值 %d" % (flag, vid, out.name, peak), flush=True)
            if peak > 500:
                ok += 1
            time.sleep(0.8)

        print("\n完成：%d / %d 个录到有效音频" % (ok, len(ids)))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
