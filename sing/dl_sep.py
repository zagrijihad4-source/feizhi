"""通用多线程下载器（hf-mirror），严格校验 206 + 大小。"""
import concurrent.futures as cf
import sys
import time
from pathlib import Path

import requests

H = {"User-Agent": "Mozilla/5.0"}
THREADS = 6
DEST = Path(r"<PROJECT_ROOT>\sing\pretrained_models\SoulX-Singer-Preprocess")

FILES = [
    ("Soul-AILab/SoulX-Singer-Preprocess",
     "mel-band-roformer-karaoke/mel_band_roformer_karaoke_becruily.ckpt",
     DEST / "mel-band-roformer-karaoke" / "mel_band_roformer_karaoke_becruily.ckpt"),
]


def fetch(url, start, end, path):
    want = end - start + 1
    for _ in range(5):
        try:
            h = dict(H, Range="bytes=%d-%d" % (start, end))
            with requests.get(url, headers=h, timeout=120, stream=True) as r:
                if r.status_code != 206:
                    time.sleep(1.5)
                    continue
                buf = bytearray()
                for chunk in r.iter_content(1024 * 256):
                    buf.extend(chunk)
                    if len(buf) > want:
                        break
                if len(buf) != want:
                    time.sleep(1.5)
                    continue
                with open(path, "r+b") as fh:
                    fh.seek(start)
                    fh.write(buf)
                return len(buf)
        except Exception:
            time.sleep(1.5)
    return 0


def dl(repo, fname, out):
    if out.exists() and out.stat().st_size > 1024 * 1024:
        print("[skip]", out.name, "%.0f MB" % (out.stat().st_size / 1048576))
        return True
    url = "https://hf-mirror.com/%s/resolve/main/%s" % (repo, fname)
    r = requests.head(url, headers=H, timeout=30, allow_redirects=True)
    total = int(r.headers.get("Content-Length") or 0)
    print("[get ] %s %.0f MB" % (out.name, total / 1048576), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.truncate(total)
    step = (total + THREADS - 1) // THREADS
    jobs = [(i * step, min(total - 1, i * step + step - 1)) for i in range(THREADS)]
    t0 = time.time()
    done = 0
    with cf.ThreadPoolExecutor(max_workers=THREADS) as ex:
        for f in cf.as_completed([ex.submit(fetch, url, s, e, tmp) for s, e in jobs]):
            done += f.result()
            print("   %.1f%%  %.0f/%.0f MB  %.1f MB/s"
                  % (done * 100.0 / total, done / 1048576, total / 1048576,
                     done / 1048576 / max(0.1, time.time() - t0)), flush=True)
    if tmp.stat().st_size != total or done != total:
        print("[fail] 不完整", tmp.stat().st_size, done, total)
        return False
    tmp.replace(out)
    print("[ok  ] %s %.0f MB / %.0fs" % (out.name, total / 1048576, time.time() - t0))
    return True


ok = all(dl(repo, fname, out) for repo, fname, out in FILES)
sys.exit(0 if ok else 1)
