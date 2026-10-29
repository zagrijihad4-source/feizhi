# -*- coding: utf-8 -*-
"""探测微信 4.x 图片 dat 的真实加密规则（不猜，暴力定参）。

已知：文件头 `07 08 56 32 08 07` = V2 标志。
做法：对每个 dat，遍历 (偏移 6..160) × (XOR key 0..255)，
用**严格**魔数判定（JPEG 要 SOI+EOI，PNG 要签名+IEND，HEIC 看 ftyp），
统计全库命中的 (偏移, key, 格式) 分布 —— 若分布唯一，那就是规则。

用法:
    python probe_img_dat.py [--save]
"""
from __future__ import annotations

import binascii
import hashlib
import sys
from collections import Counter
from pathlib import Path

ATTACH = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\msg\attach")
SAVE = Path(r"<PROJECT_ROOT>\tmp\img_probe")

HEAD_V2 = bytes([0x07, 0x08, 0x56, 0x32, 0x08, 0x07])
HEAD_V1 = bytes([0x07, 0x08, 0x56, 0x31, 0x08, 0x07])


def sniff_at(buf: bytes, off: int, key: int) -> str | None:
    """在 off 处按 key 解密后，判断是不是图片起始。"""
    if off + 16 > len(buf):
        return None
    h = bytes(buf[off + i] ^ key for i in range(16))
    if h[:3] == b"\xff\xd8\xff" and buf[-2] ^ key == 0xFF and buf[-1] ^ key == 0xD9:
        return "jpg"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        tail = bytes(b ^ key for b in buf[-12:])
        if b"IEND" in tail:
            return "png"
    if h[:4] in (b"GIF8",):
        return "gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"
    if h[4:8] == b"ftyp" and h[8:12] in (b"heic", b"heix", b"mif1", b"hevc", b"msf1"):
        return "heic"
    if h[:2] == b"BM" and buf[off + 2] ^ key < 0x40:
        return "bmp"
    return None


def brute(buf: bytes) -> list[tuple[int, int, str]]:
    hits = []
    for off in range(6, 161):
        for key in range(256):
            fmt = sniff_at(buf, off, key)
            if fmt:
                hits.append((off, key, fmt))
    return hits


def main() -> int:
    save = "--save" in sys.argv
    files = sorted(ATTACH.rglob("*.dat"))
    print("dat 文件 %d 个" % len(files))
    dist = Counter()
    heads = Counter()
    ok_files = []
    for p in files:
        try:
            buf = p.read_bytes()
        except OSError:
            continue
        heads[binascii.hexlify(buf[:6]).decode()] += 1
        hits = brute(buf)
        if not hits:
            continue
        # 取最小的偏移、最低的 key 作为本文件结论
        off, key, fmt = sorted(hits, key=lambda t: (t[0], t[1]))[0]
        dist[(off, key, fmt)] += 1
        ok_files.append((p, off, key, fmt, len(hits)))

    print("\n前 6 字节分布（Top5）:")
    for h, c in heads.most_common(5):
        print("  %s  x%d" % (h, c))

    print("\n(偏移, key, 格式) 分布 Top10:")
    for (off, key, fmt), c in dist.most_common(10):
        print("  off=%-4d key=0x%02x fmt=%-5s  x%d" % (off, key, fmt, c))

    print("\n识别成功 %d / %d 个文件" % (len(ok_files), len(files)))
    for p, off, key, fmt, nh in ok_files[:12]:
        print("  %-70s off=%-3d key=0x%02x %-4s (多解 %d)"
              % (p.name, off, key, fmt, nh))

    if save:
        SAVE.mkdir(parents=True, exist_ok=True)
        for p, off, key, fmt, _ in ok_files:
            buf = p.read_bytes()
            body = bytes(b ^ key for b in buf[off:])
            out = SAVE / ("%s.%s" % (p.stem, fmt))
            out.write_bytes(body)
        print("\n已导出 %d 个到 %s" % (len(ok_files), SAVE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
