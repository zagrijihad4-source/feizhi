"""从抖音分享页（iesdouyin）拿视频真实地址。"""
import json
import re
import sys

import requests

H = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                   "Mobile/15E148 Safari/604.1"),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.iesdouyin.com/",
}

aid = sys.argv[1] if len(sys.argv) > 1 else "7534670384014495010"

URLS = [
    "https://www.iesdouyin.com/share/video/%s/" % aid,
    "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=%s" % aid,
    "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=%s&device_platform=webapp" % aid,
]

for u in URLS:
    print("===", u)
    try:
        r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
        print("  status", r.status_code, "len", len(r.text), "final", r.url[:90])
        t = r.text
        # JSON 接口
        if t.lstrip().startswith("{"):
            try:
                d = r.json()
                print("  JSON keys:", list(d.keys())[:8])
                s = json.dumps(d, ensure_ascii=False)
                urls = re.findall(r'"(?:play_addr|playAddr|download_addr|downloadAddr)[^"]*"\s*:\s*\{[^}]*?"url_list"\s*:\s*\[(.*?)\]', s, re.S)
                for uu in urls[:2]:
                    print("  play urls:", re.findall(r'"(https?://[^"]+)"', uu)[:3])
            except Exception as exc:  # noqa: BLE001
                print("  json 解析失败", exc)
        # HTML 里的 RENDER_DATA / 视频地址
        m = re.search(r'id="RENDER_DATA"[^>]*>(.*?)</script>', t, re.S)
        if m:
            import urllib.parse
            dec = urllib.parse.unquote(m.group(1))
            print("  RENDER_DATA", len(dec))
            hits = re.findall(r'https?://[^"\\]+\.mp4[^"\\]*', dec)
            print("  mp4 命中:", hits[:3])
            aid2 = re.findall(r'"awemeId"\s*:\s*"(\d+)"', dec)[:3]
            print("  awemeId:", aid2)
        hits2 = re.findall(r'https?://[^"\\\s]+\.mp4[^"\\\s]*', t)
        if hits2:
            print("  裸 mp4:", hits2[:3])
    except Exception as exc:  # noqa: BLE001
        print("  ERR", type(exc).__name__, str(exc)[:100])
