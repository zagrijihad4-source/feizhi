"""Download the two 沦陷 clips 音音子 posted on Douyin and extract their audio.

posts.json already holds the signed play URLs, so no login or yt-dlp is needed.
"""
import json
import os
import subprocess
import sys
import tempfile

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "source", "dy_lunxian")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
H = {"User-Agent": UA, "Referer": "https://www.douyin.com/", "Accept": "*/*"}
FFMPEG = r"F:\re-toolkit\bin\ffmpeg.exe"


def main():
    os.makedirs(OUT, exist_ok=True)
    posts = json.load(open(os.path.join(HERE, "douyin", "posts.json"), encoding="utf-8"))
    targets = [p for p in posts if "沦陷" in json.dumps(p, ensure_ascii=False)]
    print("targets:", len(targets))
    for p in targets:
        aid = p["aweme_id"]
        dst = os.path.join(OUT, aid + ".wav")
        if os.path.exists(dst):
            print("skip", aid)
            continue
        url = p.get("play") or ""
        if not url:
            print("no play url", aid)
            continue
        tmp = os.path.join(tempfile.gettempdir(), aid + ".mp4")
        try:
            with requests.get(url, headers=H, stream=True, timeout=90) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            size = os.path.getsize(tmp)
            cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                   "-i", tmp, "-vn", "-ac", "1", "-ar", "44100", dst]
            subprocess.run(cmd, check=True)
            print("ok  %s  video=%.1f MB  audio=%.2fs"
                  % (aid, size / 1048576, os.path.getsize(dst) / 2 / 44100))
        except Exception as e:
            print("fail", aid, type(e).__name__, str(e)[:100])
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


if __name__ == "__main__":
    main()
