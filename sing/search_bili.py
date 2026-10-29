"""在 B 站搜《潮汐 傅梦彤》，打印候选视频的 BV 号、标题、时长。"""
import json
import re
import urllib.parse

import requests

H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
}

for kw in ["傅梦彤 潮汐", "潮汐 傅梦彤", "潮汐"]:
    q = urllib.parse.quote(kw)
    url = ("https://api.bilibili.com/x/web-interface/search/type"
           "?search_type=video&page=1&page_size=10&keyword=" + q)
    print("=== 搜索:", kw)
    try:
        r = requests.get(url, headers=H, timeout=20)
        d = r.json()
        if d.get("code") != 0:
            print("  code", d.get("code"), d.get("message"))
            continue
        items = ((d.get("data") or {}).get("result") or [])
        for it in items[:8]:
            title = re.sub(r"<[^>]+>", "", it.get("title", ""))
            print("  %-12s %-50s %s  up=%s" % (
                it.get("bvid", ""), title[:50], it.get("duration", ""),
                it.get("author", "")))
        if items:
            break
    except Exception as exc:  # noqa: BLE001
        print("  ERR", type(exc).__name__, str(exc)[:100])
