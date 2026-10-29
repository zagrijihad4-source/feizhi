"""Fetch a song's audio from Bilibili via a real browser.

yt-dlp hits HTTP 412 on bilibili search, but the page itself exposes
window.__playinfo__ with signed DASH audio URLs, so we read that instead.

usage: python bili_fetch.py "搁浅 周杰伦" [out_name]
"""
import json
import pathlib
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(r"<PROJECT_ROOT>\sing\source")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

kw = sys.argv[1] if len(sys.argv) > 1 else "搁浅 周杰伦"
name = sys.argv[2] if len(sys.argv) > 2 else "gejian"

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=False,
                          args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=UA)
    page = ctx.new_page()

    search_url = "https://search.bilibili.com/all?keyword=%s" % requests.utils.quote(kw)
    page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(4)
    try:
        page.mouse.wheel(0, 600)
        time.sleep(2)
    except Exception:
        pass

    cards = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll("a[href*='/video/BV']").forEach(a => {
            const t = (a.getAttribute('title') || a.textContent || '').trim();
            if (!t) return;
            out.push({href: a.href.split('?')[0], title: t.slice(0, 80)});
        });
        const seen = new Set();
        return out.filter(x => { if (seen.has(x.href)) return false; seen.add(x.href); return true; }).slice(0, 12);
    }""")
    print("search results:", len(cards))
    for i, c in enumerate(cards[:8]):
        print("  %d. %s | %s" % (i, c["title"][:50], c["href"]))

    if not cards:
        print("no results")
        ctx.close()
        b.close()
        raise SystemExit(1)

    # prefer a title that mentions the song and looks like the original
    pick = cards[0]
    for c in cards:
        if "搁浅" in c["title"] and "翻唱" not in c["title"] and "伴奏" not in c["title"]:
            pick = c
            break
    print("\npicked:", pick["title"], pick["href"])

    page.goto(pick["href"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(4)
    info = page.evaluate("() => window.__playinfo__ || null")
    if not info:
        time.sleep(3)
        info = page.evaluate("() => window.__playinfo__ || null")
    ctx.close()
    b.close()

if not info:
    print("no __playinfo__")
    raise SystemExit(2)

dash = (info.get("data") or {}).get("dash") or {}
audios = dash.get("audio") or []
if not audios:
    print("no dash audio; keys:", list((info.get("data") or {}).keys()))
    raise SystemExit(3)

audios.sort(key=lambda a: a.get("bandwidth") or 0, reverse=True)
best = audios[0]
url = best.get("baseUrl") or best.get("base_url")
print("audio: id=%s bandwidth=%s kbps" % (best.get("id"), int((best.get("bandwidth") or 0) / 1000)))

h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}
dst = OUT / ("%s.m4a" % name)
with requests.get(url, headers=h, stream=True, timeout=120) as r:
    if r.status_code != 200:
        print("download failed http", r.status_code)
        raise SystemExit(4)
    n = 0
    with open(dst, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            if chunk:
                f.write(chunk)
                n += len(chunk)
print("saved %s  %.1f MB" % (dst, n / 1048576))
