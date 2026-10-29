"""Extract video id + title + duration + author from the Douyin search page.

Runs a visible persistent Chrome (headless is captcha-walled) but never moves
the mouse or steals focus; it only reads the DOM.
"""
import json
import os
import re
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "douyin", "profile")
OUT = os.path.join(HERE, "douyin", "search_cards.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
KW = sys.argv[1] if len(sys.argv) > 1 else "樱花树下的约定 旺仔小乔"

JS = r"""
() => {
  const out = [];
  document.querySelectorAll('a[href*="/video/"]').forEach(a => {
    const m = a.href.match(/\/video\/(\d+)/);
    if (!m) return;
    const txt = (a.innerText || '').replace(/\s+/g, ' ').trim();
    out.push({id: m[1], text: txt.slice(0, 160)});
  });
  return out;
}
"""


def main():
    url = "https://www.douyin.com/search/" + urllib.parse.quote(KW) + "?type=video"
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False, no_viewport=True,
            user_agent=UA,
            args=["--mute-audio", "--disable-blink-features=AutomationControlled",
                  "--window-position=60,60", "--window-size=1280,900"],
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(7000)
        for _ in range(3):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(1500)
        cards = page.evaluate(JS)
        seen, rows = set(), []
        for c in cards:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            rows.append(c)
        print("cards:", len(rows))
        for r in rows:
            print("  %s | %s" % (r["id"], r["text"]))
        json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved", OUT)
        page.wait_for_timeout(1200)
        ctx.close()


if __name__ == "__main__":
    main()
