"""dump 任意文件的前 N 字节（hex + ASCII + 字符串候选）。

用途：检查微信表情加密文件的头部结构，找明文元数据（fileid / url / md5）。

用法:
    python dump_file.py "D:\\path\\to\\file" 256
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    p = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    data = p.read_bytes()
    blk = data[:n]
    print(f"{p.name}  size={len(data)}  显示前 {len(blk)} 字节")
    print(f"magic: {' '.join(f'{b:02x}' for b in blk[:8])}")
    for j in range(0, len(blk), 16):
        row = blk[j:j + 16]
        hexs = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"  +{j:04x}  {hexs:<48}  {asc}")

    # 抽出可见 ASCII 串（长度 >= 6），看有没有 url / id / md5
    strs = [m.group(0).decode("ascii", "replace")
            for m in re.finditer(rb"[\x20-\x7e]{6,}", data[:4096])]
    if strs:
        print("\n可见 ASCII 串（前 4096 字节内）:")
        for s in strs[:40]:
            print(f"  {s[:160]}")
    else:
        print("\n前 4096 字节内无长度 >=6 的可见 ASCII 串")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
