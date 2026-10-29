"""Search Weixin.dll for ASCII/UTF-16 strings and report their RVAs.

Usage: python find_str.py <pattern> [pattern ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    pats = sys.argv[1:] or ["CustomEmotion", "CustomSmiley", "Persist", "emoticon"]
    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    secs = []
    for s in pe.sections:
        secs.append((s.Name.rstrip(b"\x00").decode("ascii", "replace"),
                     s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData))

    def rva_of(off: int):
        for name, va, rp, rs in secs:
            if rp <= off < rp + rs:
                return va + (off - rp), name
        return None, None

    for pat in pats:
        for enc, tag in (("ascii", "a"), ("utf-16-le", "w")):
            needle = pat.encode(enc)
            hits = []
            start = 0
            while len(hits) < 8:
                i = data.find(needle, start)
                if i < 0:
                    break
                start = i + 1
                rva, sec = rva_of(i)
                if rva is None:
                    continue
                if sec == ".text":
                    continue          # code bytes, not a real string
                hits.append((rva, sec))
            if not hits:
                continue
            print(f"== {pat} ({tag}) : {len(hits)}")
            for rva, sec in hits:
                print(f"   rva={rva:#010x} sec={sec}")
                for name, va, rp, rs in secs:
                    if va <= rva < va + rs:
                        o = rp + (rva - va)
                        ctx = data[max(0, o - 40):o + 120]
                        txt = "".join(chr(c) if 32 <= c < 127 else "." for c in ctx)
                        print(f"      ctx: {txt}")
                        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
