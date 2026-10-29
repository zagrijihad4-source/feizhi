"""Fetch the two 沦陷 clips by driving a real browser through the saved session.

The static page is a JS shell, so the play URL only exists in the API response
the page itself receives. Capture those responses and pull play_addr out.
"""
import json
import os
import re
import subprocess
import tempfile

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "source", "dy_lunxian")
STATE = os.path.join(HERE, "douyin", "storage_state.json")
FFMPEG = "ffmpeg"
IDS = ["7692385788924171347", "7047072469190053153"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

hits = []


def scrape_urls_from_json(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("play_addr", "playAddr", "play_addr_h264", "download_addr"):
                if isinstance(v, dict):
                    for u in v.get("url_list", []) or []:
                        if isinstance(u, str) and "http" in u:
                            out.add(u)
                elif isinstance(v, list):
                    for u in v:
                        if isinstance(u, str) and "http" in u:
                            out.add(u)
            else:
                scrape_urls_from_json(v, out)
    elif isinstance(obj, list):
        for v in obj:
            scrape_urls_from_json(v, out)


def main():
    os.makedirs(OUT, exist_ok=True)
    urls = set()

    def on_response(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if not any(t in ct for t in ("json", "text", "javascript", "protobuf")):
                return
            body = resp.text()
        except Exception:
            return
        if "play_addr" in body or "playAddr" in body or "douyinvod" in body:
            hits.append(body)
            for m in re.finditer(r'(https?:[\\/]+[^\s"\'\\]*douyinvod[^\s"\'\\]*)', body):
                urls.add(m.group(1).replace("\\u002F", "/").replace("\\/", "/"))

    with sync_playwright() as p:
        # playwright's bundled chromium cannot be downloaded here (CDN blocked),
        # so drive the Chrome that is already installed on this machine.
        browser = None
        for ch in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=ch, headless=True, args=["--mute-audio"])
                print("browser: system", ch)
                break
            except Exception as e:
                print("launch %s failed: %s" % (ch, str(e)[:80]))
        if browser is None:
            raise SystemExit("no usable browser channel")
        ctx = browser.new_context(storage_state=STATE if os.path.exists(STATE) else None,
                                  no_viewport=True, user_agent=UA)
        ctx.on("response", on_response)
        page = ctx.new_page()
        for aid in IDS:
            hits.clear()
            urls.clear()
            dst = os.path.join(OUT, aid + ".wav")
            if os.path.exists(dst):
                print("skip", aid)
                continue
            print("open", aid)
            try:
                page.goto("https://www.douyin.com/video/%s" % aid,
                          wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(9000)
            except Exception as e:
                print("  nav fail", type(e).__name__, str(e)[:90])
            print("  captured responses=%d urls=%d" % (len(hits), len(urls)))
            got = False
            # CDN wants Origin + Referer + the session cookies; plain requests
            # (or ctx.request) gets 403 without all three.
            import requests as _rq
            ck = {}
            try:
                st = json.load(open(STATE, encoding="utf-8"))
                ck = {c["name"]: c["value"] for c in st.get("cookies", []) if c.get("name")}
            except Exception:
                pass
            hh = {"User-Agent": UA,
                  "Referer": "https://www.douyin.com/",
                  "Origin": "https://www.douyin.com",
                  "Accept": "*/*",
                  "Accept-Language": "zh-CN,zh;q=0.9"}
            # only the v11-weba host serves these clips; prime/cold2 always 403
            ordered = sorted(urls, key=lambda u: 0 if "v11-weba" in u else 1)
            for u in ordered[:12]:
                tmp = os.path.join(tempfile.gettempdir(), aid + ".mp4")
                try:
                    v = _rq.get(u, headers=hh, cookies=ck, stream=True, timeout=120)
                    print("   try %s -> %d" % (u[:60], v.status_code))
                    if v.status_code not in (200, 206):
                        continue
                    total = 0
                    with open(tmp, "wb") as f:
                        for chunk in v.iter_content(1 << 16):
                            if chunk:
                                f.write(chunk)
                                total += len(chunk)
                    print("   got %d bytes" % total)
                    if total < 50000:
                        continue
                    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                                    "-i", tmp, "-vn", "-ac", "1", "-ar", "44100", dst], check=True)
                    print("   OK %.2fs" % (os.path.getsize(dst) / 2 / 44100))
                    got = True
                    break
                except Exception as e:
                    print("   dl fail", type(e).__name__, str(e)[:80])
            if not got:
                print("  FAILED", aid)
        try:
            ctx.storage_state(path=STATE)
        except Exception:
            pass
        browser.close()


if __name__ == "__main__":
    main()
