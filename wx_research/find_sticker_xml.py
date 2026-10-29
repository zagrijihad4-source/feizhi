"""Search Weixin.dll for sticker/emoji message XML fragments and field names.

If WeChat builds emoji messages from an XML template, the template strings live
in .rdata. Finding them tells us exactly what the message body must contain,
without needing to reverse the serializer.

Usage: python find_sticker_xml.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000

PATTERNS = [
    b"<emoji",
    b"<msg><emoji",
    b"cdnthumburl",
    b"cdnthumbaeskey",
    b"cdnthumbwidth",
    b"cdnthumbheight",
    b"cdnthumblength",
    b"encryver",
    b"idbuffer",
    b"productid",
    b"emojiattr",
    b"emoticon",
    b"aeskey",
    b"<img aeskey",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()

    secs = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\x00").decode("ascii", "replace")
        secs.append((name, s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData))

    def rva_of(off: int):
        for name, va, rp, rs in secs:
            if rp <= off < rp + rs:
                return va + (off - rp), name
        return None, None

    for pat in PATTERNS:
        hits = []
        start = 0
        while True:
            i = data.find(pat, start)
            if i < 0:
                break
            start = i + 1
            rva, sname = rva_of(i)
            if rva is None:
                continue
            hits.append((rva, sname))
            if len(hits) >= 6:
                break
        print(f"== {pat.decode()} : {len(hits)} shown")
        for rva, sname in hits:
            off = i
            # print a window of printable text around the first hit only
            print(f"   rva={rva:#010x} sec={sname}")
        if hits:
            rva, _ = hits[0]
            # locate raw offset again for the first hit
            for name, va, rp, rs in secs:
                if va <= rva < va + rs:
                    o = rp + (rva - va)
                    ctx = data[o:o + 400]
                    txt = "".join(chr(c) if 32 <= c < 127 else "." for c in ctx)
                    print(f"   ctx: {txt}")
                    break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
