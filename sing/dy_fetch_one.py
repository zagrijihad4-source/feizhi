"""Download one Douyin video's audio by aweme id, using the logged-in profile.

CDN only serves media to the v11-weba host and only with Origin/Referer/cookies,
so the page is opened in a real profile, play_addr is harvested from the API
responses the page itself makes, and the file is fetched with those headers.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import requests
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "douyin", "profile")
STATE = os.path.join(HERE, "douyin", "storage_state.json")
OUT = os.path.join(HERE, "source", "sakura")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

urls = set()
meta = {}


def main():
    aid = sys.argv[1] if len(sys.argv) > 1 else "7460027099898727739"
    tag = sys.argv[2] if len(sys.argv) > 2 else "wz_dy"
    os.makedirs(OUT, exist_ok=True)

    target_id = aid
    dur_target = [None]

    def collect_play(obj, sink):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("play_addr", "playAddr", "play_addr_h264", "download_addr"):
                    if isinstance(v, dict):
                        for u in v.get("url_list", []) or []:
                            if isinstance(u, str) and "http" in u:
                                sink.add(u)
                    elif isinstance(v, list):
                        for u in v:
                            if isinstance(u, str) and "http" in u:
                                sink.add(u)
                else:
                    collect_play(v, sink)
        elif isinstance(obj, list):
            for v in obj:
                collect_play(v, sink)

    def find_aweme(obj, sink):
        """Only take play urls that belong to the requested aweme id."""
        if isinstance(obj, dict):
            if str(obj.get("aweme_id") or "") == target_id:
                collect_play(obj, sink)
                d = obj.get("duration") or (obj.get("video") or {}).get("duration")
                if d:
                    dur_target[0] = int(d)
                desc = obj.get("desc")
                if desc:
                    meta["desc"] = desc
            for v in obj.values():
                find_aweme(v, sink)
        elif isinstance(obj, list):
            for v in obj:
                find_aweme(v, sink)

    def on_response(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if "json" not in ct:
                return
            body = resp.text()
        except Exception:
            return
        if target_id not in body:
            return
        try:
            data = json.loads(body)
        except Exception:
            return
        find_aweme(data, urls)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False, no_viewport=True, user_agent=UA,
            args=["--mute-audio", "--disable-blink-features=AutomationControlled",
                  "--window-position=60,60", "--window-size=1280,900"],
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        ctx.on("response", on_response)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.douyin.com/video/%s" % aid,
                  wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(9000)
        print("captured urls:", len(urls), "| desc:", (meta.get("desc") or "")[:60],
              "| dur:", meta.get("duration_ms"))

        ck = {}
        if os.path.exists(STATE):
            st = json.load(open(STATE, encoding="utf-8"))
            ck = {c["name"]: c["value"] for c in st.get("cookies", []) if c.get("name")}
        hh = {"User-Agent": UA, "Referer": "https://www.douyin.com/",
              "Origin": "https://www.douyin.com", "Accept": "*/*"}
        ordered = sorted(urls, key=lambda u: 0 if "v11-weba" in u else 1)
        dst = os.path.join(OUT, tag + ".wav")
        if os.path.exists(dst):
            os.remove(dst)
        for idx, u in enumerate(ordered[:14]):
            tmp = os.path.join(tempfile.gettempdir(), "%s_%d.mp4" % (aid, idx))
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                r = requests.get(u, headers=hh, cookies=ck, stream=True, timeout=120)
                if r.status_code not in (200, 206):
                    continue
                total = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)
                if total < 50000:
                    continue
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                                "-i", tmp, "-vn", "-ac", "1", "-ar", "44100", dst], check=True)
                dur = os.path.getsize(dst) / 2 / 44100
                if dur < 5 or dur > 400:
                    print("  reject %.1fs (implausible)" % dur)
                    os.remove(dst)
                    continue
                print("OK %.2fs  %.1f MB  -> %s" % (dur, os.path.getsize(dst) / 1048576, dst))
                break
            except Exception as e:
                print("  fail", type(e).__name__, str(e)[:70])
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        ctx.close()


if __name__ == "__main__":
    main()
