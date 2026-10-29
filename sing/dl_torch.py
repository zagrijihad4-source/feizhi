"""多线程下载 torch wheel 并本地安装（pip 直连 2.4GB 会卡死）。"""
import concurrent.futures as cf
import os
import sys
import time
from pathlib import Path

import requests

WHEEL_DIR = Path(r"<PROJECT_ROOT>\sing\wheels")
WHEEL_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    ("torch", "https://download.pytorch.org/whl/cu121/torch-2.2.0%2Bcu121-cp310-cp310-win_amd64.whl"),
    ("torchaudio", "https://download.pytorch.org/whl/cu121/torchaudio-2.2.0%2Bcu121-cp310-cp310-win_amd64.whl"),
]

H = {"User-Agent": "Mozilla/5.0"}
THREADS = 8
CHUNK = 8 * 1024 * 1024


def head_size(url: str) -> int:
    r = requests.head(url, headers=H, timeout=30, allow_redirects=True)
    return int(r.headers.get("Content-Length") or 0)


def fetch_range(url: str, i: int, start: int, end: int, out: Path) -> int:
    for attempt in range(4):
        try:
            h = dict(H, Range="bytes=%d-%d" % (start, end))
            r = requests.get(url, headers=h, timeout=90, stream=True)
            if r.status_code not in (200, 206):
                time.sleep(2)
                continue
            got = 0
            with open(out, "r+b") as fh:
                fh.seek(start)
                for chunk in r.iter_content(1024 * 512):
                    fh.write(chunk)
                    got += len(chunk)
            return got
        except Exception:
            time.sleep(2)
    return 0


def download(name: str, url: str) -> Path | None:
    out = WHEEL_DIR / (name + ".whl")
    if out.exists() and out.stat().st_size > 1024 * 1024:
        print("[skip] %s 已存在 %.0f MB" % (out.name, out.stat().st_size / 1048576))
        return out
    total = head_size(url)
    if total <= 0:
        print("[fail] %s 拿不到文件大小" % name)
        return None
    print("[get ] %s  %.0f MB" % (name, total / 1048576), flush=True)
    part = out.with_suffix(".part")
    with open(part, "wb") as fh:
        fh.truncate(total)

    n = THREADS
    step = (total + n - 1) // n
    ranges = []
    for i in range(n):
        s = i * step
        e = min(total - 1, s + step - 1)
        if s <= e:
            ranges.append((i, s, e))

    t0 = time.time()
    done = 0
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(fetch_range, url, i, s, e, part) for i, s, e in ranges]
        for f in cf.as_completed(futs):
            got = f.result()
            done += got
            el = max(0.1, time.time() - t0)
            print("   %.1f%%  %.0f/%.0f MB  %.1f MB/s"
                  % (done * 100.0 / total, done / 1048576, total / 1048576,
                     done / 1048576 / el), flush=True)

    if part.stat().st_size == total:
        part.replace(out)
        print("[ok  ] %s %.0f MB / %.0fs" % (out.name, total / 1048576, time.time() - t0))
        return out

    # 分块不完整的话，退回单线程重下
    print("[warn] 分块不完整 %d/%d，单线程重下" % (part.stat().st_size, total))
    got = 0
    with requests.get(url, headers=H, timeout=120, stream=True) as r:
        with open(part, "wb") as fh:
            for chunk in r.iter_content(1024 * 512):
                fh.write(chunk)
                got += len(chunk)
                if got % (64 * 1024 * 1024) < 1024 * 512:
                    print("   %.1f%%  %.0f MB" % (got * 100.0 / total, got / 1048576), flush=True)
    if part.stat().st_size == total:
        part.replace(out)
        print("[ok  ] %s（单线程）" % out.name)
        return out
    print("[fail] %s 仍不完整" % name)
    return None


if __name__ == "__main__":
    got = []
    for name, url in CANDIDATES:
        p = download(name, url)
        if p:
            got.append(p)
    print("\n下到 %d 个 wheel：" % len(got))
    for g in got:
        print("  ", g)
    sys.exit(0 if len(got) == len(CANDIDATES) else 1)
