"""Search Douyin for 旺仔小乔's 樱花树下的约定 with a real, visible Chrome.

Headless gets captcha-walled, so this runs a persistent (real-profile) Chrome
with automation flags suppressed. It never moves the mouse or steals focus.
If a captcha appears, the operator solves it; this script just keeps polling
until video links show up, then reports them.
"""
import json
import os
import re
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "douyin", "profile")
KEYS = os.path.join(HERE, "douyin", "search_keys.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
KW = sys.argv[1] if len(sys.argv) > 1 else "樱花树下的约定 旺仔小乔"
MAX_WAIT = 300


def main():
    os.makedirs(PROFILE, exist_ok=True)
    url = "https://www.douyin.com/search/" + urllib.parse.quote(KW) + "?type=video"
    found = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            channel="chrome",
            headless=False,
            no_viewport=True,
            user_agent=UA,
            args=[
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",
                "--window-position=60,60",
                "--window-size=1280,900",
            ],
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                body = resp.text()
            except Exception:
                return
            if "aweme_id" not in body:
                return
            for m in re.finditer(r'"aweme_id"\s*:\s*"(\d{15,25})"', body):
                found.setdefault(m.group(1), {})
            for m in re.finditer(r'"desc"\s*:\s*"([^"]{0,80})"', body):
                pass

        ctx.on("response", on_response)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        print("opened search page; waiting for results (solve any captcha by hand)", flush=True)

        t0 = time.time()
        while time.time() - t0 < MAX_WAIT:
            html = page.content()
            ids = sorted(set(re.findall(r'/video/(\d{15,25})', html)))
            if ids:
                for i in ids:
                    found.setdefault(i, {})
                print("DOM video ids:", len(ids), ids[:10], flush=True)
                break
            time.sleep(3)
            try:
                page.mouse.wheel(0, 1200)
            except Exception:
                pass

        html = page.content()
        ids = sorted(set(re.findall(r'/video/(\d{15,25})', html)))
        for i in ids:
            found.setdefault(i, {})
        print("total candidate ids:", len(found), flush=True)

        # grab titles next to each id if present
        pairs = re.findall(r'/video/(\d{15,25})[^>]*>.{0,400}?', html)
        json.dump({"keyword": KW, "ids": list(found.keys())}, open(KEYS, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("saved", KEYS, flush=True)
        page.screenshot(path=os.path.join(HERE, "outputs", "dy_search2.png"), full_page=False)
        print("screenshot -> outputs/dy_search2.png", flush=True)
        # leave the window open a moment so the operator can see it
        page.wait_for_timeout(2500)
        ctx.close()


if __name__ == "__main__":
    main()
