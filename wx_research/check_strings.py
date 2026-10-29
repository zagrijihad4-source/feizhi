"""按 RVA 精确读取 Weixin.dll 中的字符串，验证反汇编里看到的 lea 目标。"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")

# 想核对的 RVA（来自 r2 反汇编中的 lea 目标）
CHECK = [
    0x07FB7326,
    0x07FB7CE4,
    0x080D7AF0,
    0x080D854C,
    0x080D85E2,
    0x08012A09,
    0x08422242,
    0x0842224F,
    0x08421685,
    0x08421709,
]


def parse_pe_sections(data: bytes):
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    num_sec = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(num_sec):
        o = sec_off + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, va, vsize, rawptr, rawsize))
    return out


def rva_to_off(sections, rva):
    for _n, va, vsize, rawptr, rawsize in sections:
        if va <= rva < va + max(vsize, rawsize):
            off = rawptr + (rva - va)
            if off < rawptr + rawsize:
                return off
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    data = DLL.read_bytes()
    sections = parse_pe_sections(data)
    for rva in CHECK:
        off = rva_to_off(sections, rva)
        if off is None:
            print(f"RVA {rva:#010x}: 未映射")
            continue
        raw = data[off:off + 80]
        s = raw.split(b"\0")[0]
        try:
            txt = s.decode("utf-8")
        except UnicodeDecodeError:
            txt = s.decode("latin-1")
        printable = sum(1 for c in txt if 32 <= ord(c) < 127)
        flag = "TEXT" if txt and printable / max(len(txt), 1) > 0.85 else "BIN?"
        print(f"RVA {rva:#010x} off={off:#010x} len={len(s):<3} [{flag}] {txt[:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
