"""搜索 PE 里的 MSVC RTTI 类名字符串（形如 .?AVClassName@@ / .?AUStruct@@）。

用途：判断 PE 是否保留 RTTI 名字；若保留，可批量列出类名，
     再按名字反查 vtable（TypeDescriptor RVA - 0x10 → COL → pSelf）。

用法:
    python find_classnames.py              # 统计 + 采样 40 条
    python find_classnames.py Sticker      # 过滤含关键词的名字
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
PAT = re.compile(rb"\.\?A[VU]([A-Za-z0-9_@?$<>:,\-]{3,200})@@")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)

    def sec_of_off(off):
        for s in pe.sections:
            a = s.PointerToRawData
            b = a + s.SizeOfRawData
            if a <= off < b:
                return s.Name.rstrip(b"\0").decode("ascii", "replace"), off - a + s.VirtualAddress
        return None, None

    hits = []
    for m in PAT.finditer(data):
        name = m.group(1).decode("ascii", "replace")
        sec, rva = sec_of_off(m.start())
        hits.append((name, sec, rva))
    print(f"RTTI 类名总数: {len(hits)}")
    if not hits:
        print("→ PE 未保留 RTTI 名字（/GR- 或名字被裁剪）")
        return 0

    seen = set()
    shown = 0
    for name, sec, rva in hits:
        if kw and kw.lower() not in name.lower():
            continue
        if name in seen:
            continue
        seen.add(name)
        print(f"  {sec} rva={rva:#010x}  {name}")
        shown += 1
        if shown >= 200:
            print("  ...(截断)")
            break
    print(f"显示 {shown} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
