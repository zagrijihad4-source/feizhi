"""从国内 GitHub 代理拉 SoulX-Singer 源码（tarball），并解压。"""
import io
import sys
import tarfile
import time
from pathlib import Path

import requests

DEST = Path(r"<PROJECT_ROOT>\sing")
MIRS = [
    "https://ghproxy.net/https://github.com/Soul-AILab/SoulX-Singer/archive/refs/heads/main.tar.gz",
    "https://ghfast.top/https://github.com/Soul-AILab/SoulX-Singer/archive/refs/heads/main.tar.gz",
    "https://gh-proxy.com/https://github.com/Soul-AILab/SoulX-Singer/archive/refs/heads/main.tar.gz",
    "https://codeload.github.com/Soul-AILab/SoulX-Singer/tar.gz/refs/heads/main",
]

H = {"User-Agent": "Mozilla/5.0"}

for url in MIRS:
    host = url.split("/")[2]
    print("== 尝试", host)
    try:
        t0 = time.time()
        r = requests.get(url, headers=H, timeout=40, stream=True)
        if r.status_code != 200:
            print("   HTTP", r.status_code)
            continue
        buf = io.BytesIO()
        total = 0
        for chunk in r.iter_content(65536):
            buf.write(chunk)
            total += len(chunk)
            if total > 80 * 1024 * 1024:
                break
        print("   下载 %.1f MB / %.1fs" % (total / 1048576, time.time() - t0))
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:gz") as tf:
            names = tf.getnames()
            root = names[0].split("/")[0]
            print("   根目录:", root)
            target = DEST / "SoulX-Singer"
            if target.exists():
                print("   已存在，跳过解压")
            else:
                tf.extractall(DEST)
                extracted = DEST / root
                if extracted.exists() and extracted != target:
                    extracted.rename(target)
            print("   OK ->", target)
            sub = sorted(p.relative_to(target).as_posix() for p in target.rglob("*")
                         if p.is_file())[:25]
            print("   文件示例:")
            for s in sub:
                print("     ", s)
            sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print("   失败:", type(exc).__name__, str(exc)[:120])

print("\n所有镜像都失败")
sys.exit(1)
