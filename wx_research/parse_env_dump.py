"""解析 env_dump.json：把抓到的信封全文还原成结构化字段视图。

关键事实（运行时 + 静态双证）：
  Envelope: vtable 0x82CB8D8(@body+0)，+0xd8 = 0x2F(收藏表情类型码)，
            +0xb0 接收者 wxid，+0x600 UUID
  Pack 对象: vtable 0x82C02B8，+8/+0x10 是 vector<shared_ptr<Content>> 区间

本脚本输出：
  1. 信封每 0x10 字节的 qword 视图，标注哪些值像指针（DLL / 堆 / 栈）
  2. 自动识别 MSVC std::string（buf/len/cap 布局，cap<=0xF 为 SSO）
  3. 对落在堆上的指针，试读其指向对象的 vtable
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import frida  # 仅用于 attach 后读内存的可选路径；本脚本只做离线解析

REPORT = Path(r"<PROJECT_ROOT>\reports\env_dump.json")
DLL_BASE = 0x7FFC9F060000
DLL_LO, DLL_HI = DLL_BASE, DLL_BASE + 0x10000000
HEAP_LO, HEAP_HI = 0x0000010000000000, 0x0000800000000000


def classify(v: int) -> str:
    if v == 0:
        return "null"
    if DLL_LO <= v < DLL_HI:
        return f"DLL+{v - DLL_BASE:#x}"
    if 0x00007FF000000000 <= v < 0x0000800000000000:
        return "mod?"
    if 0x0000010000000000 <= v < 0x0000800000000000:
        return "heap"
    if v < 0x10000:
        return f"small({v})"
    return "?"


def try_string(blk: bytes, off: int, limit: int = 0x400) -> str | None:
    """尝试把 blk[off:] 解释为 MSVC std::string。"""
    if off + 0x20 > len(blk):
        return None
    cap = struct.unpack_from("<Q", blk, off + 0x18)[0]
    ln = struct.unpack_from("<Q", blk, off + 0x10)[0]
    if ln == 0 or ln > limit:
        return None
    if cap <= 0xF:
        raw = blk[off:off + ln]
    else:
        p = struct.unpack_from("<Q", blk, off)[0]
        if not (HEAP_LO <= p < HEAP_HI):
            return None
        return f"<堆缓冲 {p:#x}, len={ln}, cap={cap}>"
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not s or any(ord(c) < 0x20 and c not in "\t\n\r" for c in s):
        return None
    return s


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not REPORT.exists():
        print(f"没有 {REPORT}")
        return 1
    data = json.loads(REPORT.read_text(encoding="utf-8"))

    print("=" * 78)
    print("## 事件概览")
    for e in data.get("events", []):
        print(f"   {e.get('kind'):12s} caller_rva={e.get('caller_rva')}")
    for s in data.get("sends", []):
        print(f"   {'send':12s} caller_rva={s.get('caller_rva')} env={s.get('env')} "
              f"vt_rva={s.get('env_vt_rva')} d8={s.get('env_d8')}")

    for i, body in enumerate(data.get("env_bodies", [])):
        hx = body.get("hex") or ""
        blk = bytes.fromhex(hx)
        print()
        print("=" * 78)
        print(f"## 信封全文 #{i}  env={body.get('env')}  {len(blk)} 字节")
        print("=" * 78)

        # 1) qword 视图
        print("\n-- qword 视图（仅显示非零且像指针/大数的项）--")
        for off in range(0, len(blk) - 7, 8):
            v = struct.unpack_from("<Q", blk, off)[0]
            cls = classify(v)
            if cls in ("null", "small(1)", "small(2)"):
                continue
            if cls == "?" or v > 0xFFFFFFFF:
                print(f"  +{off:#05x}  {v:#018x}  {cls}")

        # 2) 字符串视图
        print("\n-- MSVC std::string 识别（stride 扫描）--")
        seen = set()
        for off in range(0, len(blk) - 0x20, 8):
            s = try_string(blk, off)
            if s and (off, s) not in seen:
                seen.add((off, s))
                print(f"  +{off:#05x}  len={struct.unpack_from('<Q', blk, off+0x10)[0]:<4}  {s[:120]!r}")
        if not seen:
            print("  （未识别到内联字符串）")

        # 3) 已知锚点核对
        print("\n-- 已知锚点 --")
        for off, name in ((0x0b0, "接收者 wxid"), (0x600, "UUID"), (0x0d8, "类型码")):
            if off + 8 <= len(blk):
                if name == "类型码":
                    v = struct.unpack_from("<I", blk, off)[0]
                    print(f"  +{off:#05x}  {name} = {v} ({v:#x})")
                else:
                    s = try_string(blk, off)
                    v = struct.unpack_from("<Q", blk, off)[0]
                    print(f"  +{off:#05x}  {name}: str={s!r}  qword={v:#x} ({classify(v)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
