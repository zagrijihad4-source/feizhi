"""下载 7 个收藏表情模板的原图，用于人工对照。

收藏表情本体在本地是加密存储的（Persist\\<hh>\\<md5>，magic d0b168c53ac95057），
但 CDN 上的副本是明文 PNG，且 URL 里的 md5/filekey/storeid 本地可复用
（TASK_LOG §3.2），因此可以直接取原图做对照。

用法: python fetch_sticker_images.py
输出: tmp\\stk\\<idx>_<lib_md5>.png
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>")
from frida_sticker_swap import TEMPLATES  # noqa: E402

OUT = Path(r"<PROJECT_ROOT>\tmp\stk")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for i, t in enumerate(TEMPLATES):
        dst = OUT / f"{i}_{t['lib_md5']}.png"
        try:
            req = urllib.request.Request(
                t["url_20401"], headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=25).read()
            dst.write_bytes(data)
            head = data[:8].hex()
            kind = ("png" if data[:8] == b"\x89PNG\r\n\x1a\n"
                    else "gif" if data[:6] in (b"GIF87a", b"GIF89a")
                    else "?")
            print(f"[{i}] {len(data):>8} bytes  {kind:<3} head={head}  -> {dst.name}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{i}] FAIL {type(e).__name__}: {e}")
    print(f"\n完成 {ok}/{len(TEMPLATES)}  -> {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
