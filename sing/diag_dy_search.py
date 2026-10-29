"""Diagnose the Douyin search page: what appears in the DOM and which
responses carry play addresses."""
import json
import os
import re

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "douyin", "storage_state.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
KW = "樱花树下的约定 旺仔小乔"
import urllib.parse
URL = "https://www.douyin.com/search/" + urllib.parse.quote(KW) + "?type=video"

seen = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--mute-audio"])
        ctx = browser.new_context(storage_state=STATE, no_viewport=True, user_agent=UA)

        def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct and "text" not in ct:
                    return
                body = resp.text()
            except Exception:
                return
            has = "play_addr" in body or "aweme_id" in body
            seen.append((resp.url[:110], resp.status, len(body), has, ct[:40]))

        ctx.on("response", on_response)
        page = ctx.new_page()
        print("goto", URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)
        for _ in range(4):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(1500)

        html = page.content()
        print("html length:", len(html))
        ids = sorted(set(re.findall(r'/video/(\d{15,25})', html)))
        print("video ids in DOM:", len(ids), ids[:8])
        for kw in ("验证", "登录", "captcha", "安全"):
            if kw in html:
                print("  page mentions:", kw)
        print("\nresponses with aweme/play_addr:")
        for u, st, ln, has, ct in seen:
            if has:
                print("  %d %6d %s" % (st, ln, u))
        print("\nall json responses (first 12):")
        for u, st, ln, has, ct in seen[:12]:
            print("  %d %6d %s %s" % (st, ln, u, "" if has else "(no aweme)"))
        page.screenshot(path=os.path.join(HERE, "outputs", "dy_search.png"), full_page=False)
        print("screenshot -> outputs/dy_search.png")
        browser.close()


if __name__ == "__main__":
    main()
