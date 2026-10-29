"""诊断：playwright 打开的 Edge 里，抖音视频到底有没有在播，声音去了哪。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SING = Path(r"<PROJECT_ROOT>\sing")
VID = "7534670384014495010"

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=False,
                                 args=["--autoplay-policy=no-user-gesture-required"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    print("goto…", flush=True)
    page.goto("https://www.douyin.com/video/%s" % VID,
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    print("URL:", page.url)
    print("title:", page.title())

    info = page.evaluate("""() => {
        const vs = [...document.querySelectorAll('video')];
        return {
            count: vs.length,
            items: vs.map(v => ({
                paused: v.paused, muted: v.muted, volume: v.volume,
                currentTime: v.currentTime, duration: v.duration,
                readyState: v.readyState, src: (v.currentSrc||'').slice(0,60)
            }))
        };
    }""")
    print("video 元素:", info)

    body = page.inner_text("body")[:600]
    print("\n页面文字片段:\n", body)

    shot = SING / "source" / "diag_playwright.png"
    page.screenshot(path=str(shot), full_page=False)
    print("\n截图:", shot)
    time.sleep(3)
    browser.close()
