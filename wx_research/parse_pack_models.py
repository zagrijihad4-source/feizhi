"""Parse the frida pack-model hexdumps into an annotated field table.

frida_pack_models.txt holds two dumps emitted by frida_probe_hits.py:
  * tid=7676  vt=0x805e578  -> our own fabricated TEXT message model (works)
  * tid=28800 vt=0x82cb8d8  -> WeChat's own STICKER envelope model (reference)

Both are fed to pack (0x160EBE0), so a field-by-field diff tells us exactly what
a sticker model must contain.

Usage: python parse_pack_models.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\frida_pack_models.txt")


def anno(v: int) -> str:
    if v == 0:
        return ""
    if 0x10000 <= v <= 0x7FFFFFFFFFFF:
        return f"ptr/flags"
    return ""


def dump_block(tag: str, hexs: str, nbytes: int = 0x400) -> None:
    data = bytes.fromhex(hexs)
    if nbytes:
        data = data[:nbytes]
    print(f"\n===== {tag}  ({len(data)} bytes) =====")

    # 16-byte rows: offset | qwords | ascii
    for off in range(0, len(data), 16):
        row = data[off:off + 16]
        q0 = int.from_bytes(row[0:8], "little")
        q1 = int.from_bytes(row[8:16], "little") if len(row) >= 16 else 0
        txt = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
        print(f"  +0x{off:03x}  {q0:#018x}  {q1:#018x}  |{txt}|")

    # UTF-16LE strings (min 4 chars)
    print("  --- utf16 strings ---")
    i = 0
    while i + 8 <= len(data):
        chars = []
        j = i
        while j + 2 <= len(data):
            ch = int.from_bytes(data[j:j + 2], "little")
            if 32 <= ch < 127:
                chars.append(chr(ch))
                j += 2
            else:
                break
        if len(chars) >= 5:
            print(f"    +0x{i:03x}: {''.join(chars)}")
            i = j
        else:
            i += 2

    # ASCII strings
    print("  --- ascii strings ---")
    for m in re.finditer(rb"[\x20-\x7e]{5,}", data):
        print(f"    +0x{m.start():03x}: {m.group().decode()}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print("no dump file")
        return 1

    text = SRC.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"--- pack tid=(\d+) models=1\s*\n\s*\[0\] vt=(\S+) hex=(\w+)", text)
    if not blocks:
        print("no blocks parsed")
        return 1
    for tid, vt, hexs in blocks:
        label = "TEXT(ours)" if vt.lower() == "0x805e578" else "STICKER(wechat)"
        dump_block(f"{label} tid={tid} vt={vt}", hexs, 0x400)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
