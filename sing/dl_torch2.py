"""多线程下载 torch wheel（修正版）。

上一版坏掉的原因：服务器对某些 Range 请求返回 200（整个文件），
我却照样从 start 位置写，把前面的数据覆盖了。这一版：
  - 只接受 206 Partial Content
  - 校验每块实际收到的字节数 == 请求的区间长度
  - 下完整文件再用 zipfile 验证，不合法就报错而不是交给 pip
"""
import concurrent.futures as cf
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests

URL = ("https://download.pytorch.org/whl/cu121/"
       "torch-2.2.0%2Bcu121-cp310-cp310-win_amd64.whl")
OUT = Path(r"<PROJECT_ROOT>\sing\wheels\torch-2.2.0+cu121-cp310-cp310-win_amd64.whl")
H = {"User-Agent": "Mozilla/5.0"}
THREADS = 6


def fetch(url: str, start: int, end: int, path: Path) -> int:
    want = end - start + 1
    for attempt in range(5):
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


def main() -> int:
    r = requests.head(URL, headers=H, timeout=30, allow_redirects=True)
    total = int(r.headers.get("Content-Length") or 0)
    if total <= 0:
        print("拿不到文件大小")
        return 1
    print("总大小 %.2f MB，分 %d 块并发" % (total / 1048576, THREADS), flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name("dl.tmp")
    with open(tmp, "wb") as fh:
        fh.truncate(total)

    step = (total + THREADS - 1) // THREADS
    jobs = [(i * step, min(total - 1, i * step + step - 1)) for i in range(THREADS)]
    t0 = time.time()
    done = 0
    with cf.ThreadPoolExecutor(max_workers=THREADS) as ex:
        futs = [ex.submit(fetch, URL, s, e, tmp) for s, e in jobs]
        for f in cf.as_completed(futs):
            got = f.result()
            done += got
            print("  %.1f%%  %.0f/%.0f MB  %.1f MB/s"
                  % (done * 100.0 / total, done / 1048576, total / 1048576,
                     done / 1048576 / max(0.1, time.time() - t0)), flush=True)

    if tmp.stat().st_size != total or done != total:
        print("不完整：文件 %d / 总数 %d / 应下 %d" % (tmp.stat().st_size, done, total))
        return 2

    print("校验 zip ...", flush=True)
    try:
        with zipfile.ZipFile(tmp) as z:
            bad = z.testzip()
            n = len(z.namelist())
        print("zip OK，%d 个成员，坏块=%s" % (n, bad), flush=True)
    except Exception as exc:  # noqa: BLE001
        print("zip 校验失败:", exc, flush=True)
        return 3

    tmp.replace(OUT)
    print("完成 -> %s  %.1f MB / %.0fs" % (OUT, OUT.stat().st_size / 1048576,
                                          time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
