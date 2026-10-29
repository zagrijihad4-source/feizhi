# -*- coding: utf-8 -*-
"""探测：微信 4.x 本地图片缓存（msg/attach/*/YYYY-MM/Img/*.dat）能否解出真图，
并能否与 inbox 里的 type=3 消息 XML 对应上。

结论用于决定「收图 → 视觉识别」走本地缓存还是 CDN 下载。

用法:
    python probe_img_cache.py            # 只匹配，不落盘
    python probe_img_cache.py --save     # 解出的图另存到 tmp/img_probe/
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

INBOX = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\inbox")
ACCOUNT = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4")
ATTACH = ACCOUNT / "msg" / "attach"
SAVE_DIR = Path(r"<PROJECT_ROOT>\tmp\img_probe")

MAGICS = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF8", "gif"),
    (b"RIFF", "webp"),
    (b"BM", "bmp"),
)

_ATTR = re.compile(r'(\w+)="([^"]*)"')


def sniff(head: bytes) -> str | None:
    for magic, name in MAGICS:
        if head.startswith(magic):
            return name
    return None


def xor_key(buf: bytes) -> int | None:
    """单字节 XOR 爆破：返回能解出图片魔数的 key。"""
    for k in range(256):
        head = bytes(b ^ k for b in buf[:16])
        if sniff(head):
            return k
    return None


def load_type3() -> list[dict]:
    out = []
    for p in INBOX.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(d.get("type")) != "3":
            continue
        content = d.get("content") or ""
        attrs = dict(_ATTR.findall(content))
        out.append({
            "file": p.name,
            "peer": d.get("peerWxId"),
            "ts": int(d.get("timestamp") or 0),
            "md5": attrs.get("md5", ""),
            "origin": attrs.get("originsourcemd5", ""),
            "length": int(attrs.get("length") or 0),
            "thumb_len": int(attrs.get("cdnthumblength") or 0),
            "thumb_w": attrs.get("cdnthumbwidth", ""),
            "thumb_h": attrs.get("cdnthumbheight", ""),
            "aeskey": attrs.get("aeskey", ""),
        })
    return sorted(out, key=lambda r: r["ts"])


def main() -> int:
    save = "--save" in sys.argv
    msgs = load_type3()
    print("type=3 消息 %d 条" % len(msgs))
    for m in msgs:
        print("  ts=%d peer=%s md5=%s len=%d thumb=%d %sx%s"
              % (m["ts"], m["peer"], m["md5"], m["length"], m["thumb_len"],
                 m["thumb_w"], m["thumb_h"]))
    if not ATTACH.is_dir():
        print("attach 目录不存在: %s" % ATTACH)
        return 1

    files = []
    for p in ATTACH.rglob("*.dat"):
        try:
            st = p.stat()
        except OSError:
            continue
        files.append((p, st.st_size, st.st_mtime))
    print("\nattach 下 .dat %d 个" % len(files))

    dec = []
    fail = 0
    for p, size, mtime in files:
        try:
            buf = p.read_bytes()
        except OSError:
            fail += 1
            continue
        k = xor_key(buf)
        if k is None:
            fail += 1
            continue
        plain = bytes(b ^ k for b in buf)
        dec.append({
            "path": p, "name": p.name, "size": size, "mtime": mtime,
            "key": k, "kind": sniff(plain[:16]),
            "md5": hashlib.md5(plain).hexdigest(), "plain": plain,
        })
    print("可解密 %d 个，未识别 %d 个" % (len(dec), fail))
    if dec:
        keys = sorted({d["key"] for d in dec})
        print("XOR key 集合: %s" % ["0x%02x" % k for k in keys])

    # 匹配：md5 / 长度 / 时间（微信图片缓存 mtime ≈ 收到消息的时间）
    print("\n--- 与 type=3 消息匹配 ---")
    for m in msgs:
        hit_md5 = [d for d in dec if d["md5"] in (m["md5"], m["origin"])]
        hit_len = [d for d in dec
                   if d["size"] in (m["length"], m["thumb_len"])]
        near = [d for d in dec if abs(d["mtime"] - m["ts"]) <= 120]
        print("ts=%d md5=%s" % (m["ts"], m["md5"][:12]))
        print("   md5命中 %d 个%s" % (len(hit_md5),
                                   (" -> " + str([d["name"] for d in hit_md5])) if hit_md5 else ""))
        if hit_len:
            print("   长度命中 %s" % [(d["name"], d["size"]) for d in hit_len][:4])
        else:
            print("   长度未命中（消息 length=%d thumb=%d）" % (m["length"], m["thumb_len"]))
        if near:
            print("   ±120s 内落盘 %d 个: %s"
                  % (len(near), [(d["name"], d["size"]) for d in near][:4]))
        if save and (hit_md5 or near):
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            for d in (hit_md5 or near)[:3]:
                out = SAVE_DIR / ("%d_%s.%s" % (m["ts"], d["md5"][:8], d["kind"]))
                out.write_bytes(d["plain"])
                print("   saved -> %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
