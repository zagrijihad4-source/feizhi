"""Download 旺仔小乔's 樱花树下的约定 from Douyin.

Bilibili's copy was 99 kbps and the uploaded 深七 backing was poor, so take the
singer's own post instead: open the hashtag page, harvest the aweme API
responses, pick the longest clip, then pull its audio via the host that actually
serves media (v11-weba).
"""
import json
import os
import re
import subprocess
import tempfile

import requests
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "source", "sakura")
STATE = os.path.join(HERE, "douyin", "storage_state.json")
FFMPEG = "ffmpeg"
TAG = 'https://www.douyin.com/search/%E6%A8%B1%E8%8A%B1%E6%A0%91%E4%B8%8B%E7%9A%84%E7%BA%A6%E5%AE%9A%20%E6%97%BA%E4%BB%94%E5%B0%8F%E4%B9%94?type=video'
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

payloads = []


def walk(obj, out):
    """Collect every play_addr url_list found anywhere in the payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("play_addr", "playAddr", "download_addr"):
                if isinstance(v, dict):
                    for u in v.get("url_list", []) or []:
                        if isinstance(u, str):
                            out.setdefault("urls", set()).add(u)
                elif isinstance(v, list):
                    for u in v:
                        if isinstance(u, str):
                            out.setdefault("urls", set()).add(u)
            else:
                walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def media_urls(obj, out):
    walk(obj, out)


def main():
    os.makedirs(OUT, exist_ok=True)
    cands = {}          # aweme_id -> {"urls": set(), "dur": int, "desc": str}

    def on_response(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if not any(t in ct for t in ("json", "text", "javascript", "protobuf")):
                return
            body = resp.text()
        except Exception:
            return
        if "play_addr" not in body and "playAddr" not in body:
            return
        try:
            data = json.loads(body)
        except Exception:
            return
        found = {}
        media_urls(data, found)
        if not found.get("urls"):
            return
        # map every aweme id in this payload to its duration
        def scan(o):
            if isinstance(o, dict):
                aid = o.get("aweme_id")
                if aid and o.get("video"):
                    d = (o.get("video") or {}).get("duration") or o.get("duration") or 0
                    desc = o.get("desc") or ""
                    c = cands.setdefault(aid, {"urls": set(), "dur": int(d), "desc": desc})
                    c["urls"].update(found["urls"])
                    if desc and not c["desc"]:
                        c["desc"] = desc
                for v in o.values():
                    scan(v)
            elif isinstance(o, list):
                for v in o:
                    scan(v)
        scan(data)

    with sync_playwright() as p:
        browser = None
        for ch in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=ch, headless=True, args=["--mute-audio"])
                print("browser:", ch)
                break
            except Exception as e:
                print("launch", ch, "failed", str(e)[:60])
        ctx = browser.new_context(storage_state=STATE if os.path.exists(STATE) else None,
                                  no_viewport=True, user_agent=UA)
        ctx.on("response", on_response)
        page = ctx.new_page()
        print("open tag page ...")
        page.goto(TAG, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(6000)
        # scroll to load more
        for _ in range(10):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1800)
        print("collected awemes:", len(cands))
        ranked = sorted(cands.items(), key=lambda kv: -kv[1]["dur"])
        for aid, info in ranked[:8]:
            print("  %s  %6.1fs  %s" % (aid, info["dur"] / 1000.0, (info["desc"] or "")[:44]))

        # prefer clips that mention the song, longest first
        pick = None
        for aid, info in ranked:
            if info["dur"] < 20000:
                continue
            if "樱花" in (info["desc"] or "") or "约定" in (info["desc"] or ""):
                pick = (aid, info)
                break
        if pick is None and ranked:
            pick = ranked[0]
        if pick is None:
            print("nothing found")
            return
        aid, info = pick
        print("picked:", aid, info["dur"] / 1000.0, "s |", (info["desc"] or "")[:60])

        ck = {}
        try:
            st = json.load(open(STATE, encoding="utf-8"))
            ck = {c["name"]: c["value"] for c in st.get("cookies", []) if c.get("name")}
        except Exception:
            pass
        hh = {"User-Agent": UA, "Referer": "https://www.douyin.com/",
              "Origin": "https://www.douyin.com", "Accept": "*/*"}
        urls = sorted(info["urls"], key=lambda u: 0 if "v11-weba" in u else 1)
        for u in urls[:12]:
            tmp = os.path.join(tempfile.gettempdir(), aid + ".mp4")
            dst = os.path.join(OUT, aid + ".wav")
            try:
                r = requests.get(u, headers=hh, cookies=ck, stream=True, timeout=120)
                print("  try %s -> %d" % (u[:60], r.status_code))
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
                subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                                "-i", tmp, "-vn", "-ac", "1", "-ar", "44100", dst], check=True)
                print("  OK %.2fs  %.1f MB" % (44000 * 0 + os.path.getsize(dst) / 2 / 44100,
                                               os.path.getsize(dst) / 1048576))
                break
            except Exception as e:
                print("  fail", type(e).__name__, str(e)[:70])
        browser.close()


if __name__ == "__main__":
    main()
