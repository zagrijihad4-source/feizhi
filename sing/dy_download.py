"""Download Douyin posts from posts.json and extract 44.1k mono wav.

usage:
    python dy_download.py --test 1            # try the first N posts
    python dy_download.py --ids 123 456       # specific aweme_ids
    python dy_download.py --all               # everything in posts.json
    python dy_download.py --all --min-sec 8   # skip very short clips
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(r"<PROJECT_ROOT>\sing")
OUT = ROOT / "source" / "dy"
POSTS = ROOT / "douyin" / "posts.json"
LOG = ROOT / "douyin" / "download.log"
FFMPEG = "ffmpeg"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Referer": "https://www.douyin.com/", "Accept": "*/*"}


def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def download(url, dst_mp4):
    with requests.get(url, headers=H, stream=True, timeout=90) as r:
        if r.status_code != 200:
            return False, "http %d" % r.status_code
        total = 0
        with open(dst_mp4, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
    return total > 50000, "%.1f MB" % (total / 1048576)


def to_wav(mp4, wav):
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4),
           "-vn", "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", str(wav)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0 and wav.exists() and wav.stat().st_size > 10000, (p.stderr or "")[-200:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--ids-file")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min-sec", type=float, default=8.0)
    ap.add_argument("--redownload", action="store_true")
    args = ap.parse_args()

    rows = json.loads(POSTS.read_text(encoding="utf8"))
    if args.ids_file:
        wanted = {ln.strip() for ln in pathlib.Path(args.ids_file).read_text(encoding="utf8").splitlines() if ln.strip()}
        rows = [r for r in rows if r["aweme_id"] in wanted]
    elif args.ids:
        rows = [r for r in rows if r["aweme_id"] in set(args.ids)]
    elif args.test:
        rows = rows[: args.test]
    elif not args.all:
        ap.error("pick one of --test / --ids / --ids-file / --all")

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "douyin" / "mp4"
    tmp.mkdir(parents=True, exist_ok=True)

    ok = skip = fail = 0
    for r in rows:
        aid = r["aweme_id"]
        dur = (r.get("duration_ms") or 0) / 1000.0
        wav = OUT / ("%s.wav" % aid)
        if wav.exists() and not args.redownload:
            skip += 1
            continue
        if dur and dur < args.min_sec:
            skip += 1
            continue
        url = r.get("play") or r.get("download")
        if not url:
            fail += 1
            log("%s no url" % aid)
            continue
        mp4 = tmp / ("%s.mp4" % aid)
        good, info = download(url, mp4)
        if not good:
            fail += 1
            log("%s download failed: %s" % (aid, info))
            continue
        good, info = to_wav(mp4, wav)
        if not good:
            fail += 1
            log("%s ffmpeg failed: %s" % (aid, info))
            continue
        mp4.unlink(missing_ok=True)
        ok += 1
        log("%s ok %.1fs %s | %s" % (aid, dur, info, (r.get("desc") or "")[:40]))
        print("%s ok %.1fs" % (aid, dur), flush=True)

    print("done ok=%d skip=%d fail=%d -> %s" % (ok, skip, fail, OUT))


if __name__ == "__main__":
    sys.exit(main())
