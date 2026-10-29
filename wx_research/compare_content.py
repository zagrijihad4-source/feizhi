"""Diff our Content object against WeChat's own, both captured at pack time.

Source: reports/frida_deep.txt (lines starting with "    content: ")
  [1] from our wxb_send_sticker_pack()  (tid=33936)
  [2] from WeChat's native send         (tid=28800)

Also decodes the std::string slots (buf@+8n, len, cap) to show which md5/url
fields are populated.

Usage: python compare_content.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\frida_deep.txt")
IMAGE_BASE = 0x180000000
BASE_RUNTIME = 0x7FFC9F060000  # from the frida session


def strings_in(data: bytes) -> None:
    """Print the 12 std::string slots: buf(16B inline or ptr), len, cap."""
    for i in range(12):
        off = 0x10 + i * 0x20
        if off + 0x20 > len(data):
            break
        raw = data[off:off + 0x10]
        ln = int.from_bytes(data[off + 0x10:off + 0x18], "little")
        cap = int.from_bytes(data[off + 0x18:off + 0x20], "little")
        if cap <= 0xF:
            s = raw[:ln].decode("latin1")
            kind = "inline"
        else:
            kind = "heap"
            s = ""
        if not s and ln:
            kind += f"/len{ln}"
        print(f"    slot{i:<2} @+0x{off:03x} len={ln:<4} cap={cap:#x} [{kind}] "
              f"{s if s else ''}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    text = SRC.read_text(encoding="utf-8", errors="replace")
    blobs = re.findall(r"^\s*content: (\w+)$", text, re.M)
    if len(blobs) < 2:
        print(f"need 2 content dumps, found {len(blobs)}")
        return 1
    ours, native = bytes.fromhex(blobs[0]), bytes.fromhex(blobs[1])
    n = min(len(ours), len(native), 0x1B0)
    print(f"ours {len(ours)}B  native {len(native)}B  compare {n}B\n")

    print("=== diff (qword granularity) ===")
    diff = 0
    for off in range(0, n, 8):
        a = int.from_bytes(ours[off:off + 8], "little")
        b = int.from_bytes(native[off:off + 8], "little")
        if a != b:
            print(f"  +0x{off:03x}  ours={a:#018x}  native={b:#018x}")
            diff += 1
    print(f"  differing qwords: {diff}/{n // 8}\n")

    print("=== OURS string slots ===")
    strings_in(ours)
    print("=== NATIVE string slots ===")
    strings_in(native)

    print("\n=== raw head (64 bytes each) ===")
    for tag, d in (("ours", ours), ("native", native)):
        print(f"  {tag}: {d[:64].hex(' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
