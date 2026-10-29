"""Fetch the two 沦陷 clips using the saved Douyin login state.

posts.json holds signed URLs that have expired (403). The video detail page
still exposes a fresh play URL to a request carrying the session cookies, so
parse it out of the HTML instead of re-scraping the whole profile.
"""
import json
import os
import re
import subprocess
import tempfile

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "source", "dy_lunxian")
STATE = os.path.join(HERE, "douyin", "storage_state.json")
FFMPEG = r"F:\re-toolkit\bin\ffmpeg.exe"
IDS = ["7692385788924171347", "7047072469190053153"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def cookies():
    st = json.load(open(STATE, encoding="utf-8"))
    return {c["name"]: c["value"] for c in st.get("cookies", []) if c.get("name")}


def find_play(html):
    cands = []
    for pat in (r'"play_addr":\{[^}]*?"url_list":\[(.*?)\]',
                r'"playApi":"(https:[^"]+)"',
                r'"playAddr":\[(.*?)\]',
                r'(https://[a-z0-9\-\.]*douyinvod\.com[^"\\\s]+)'):
        for m in re.finditer(pat, html):
            seg = m.group(1)
            for u in re.findall(r'(https:[^"\\\s,]+)', seg):
                cands.append(u.replace("\\u002F", "/").replace("\\/", "/"))
    seen, out = set(), []
    for u in cands:
        if u not in seen and "douyinvod" in u:
            seen.add(u)
            out.append(u)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    H = {"User-Agent": UA, "Referer": "https://www.douyin.com/",
         "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
    for aid in IDS:
        dst = os.path.join(OUT, aid + ".wav")
        if os.path.exists(dst):
            print("skip", aid)
            continue
        page = "https://www.douyin.com/video/%s" % aid
        try:
            r = requests.get(page, headers=H, cookies=cookies(), timeout=30)
            urls = find_play(r.text)
            print("%s page=%d chars=%d urls=%d" % (aid, r.status_code, len(r.text), len(urls)))
            if not urls:
                head = r.text[:200].replace("\n", " ")
                print("   no url; head:", head)
                continue
            tmp = os.path.join(tempfile.gettempdir(), aid + ".mp4")
            ok = False
            for u in urls[:4]:
                try:
                    with requests.get(u, headers=H, cookies=cookies(), stream=True, timeout=90) as v:
                        if v.status_code != 200:
                            print("   try %s -> %d" % (u[:60], v.status_code))
                            continue
                        with open(tmp, "wb") as f:
                            for chunk in v.iter_content(1 << 16):
                                f.write(chunk)
                    if os.path.getsize(tmp) > 50000:
                        ok = True
                        break
                except Exception as e:
                    print("   try fail", type(e).__name__)
            if not ok:
                print("   download failed")
                continue
            subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                            "-i", tmp, "-vn", "-ac", "1", "-ar", "44100", dst], check=True)
            print("   OK %.2fs" % (os.path.getsize(dst) / 2 / 44100))
        except Exception as e:
            print("fail", aid, type(e).__name__, str(e)[:120])


if __name__ == "__main__":
    main()
