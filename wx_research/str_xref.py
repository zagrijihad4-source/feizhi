"""通用字符串 xref：给若干字符串，找出它们在 DLL 里的位置、
以及引用它们的代码（含所属函数）。

用途：定位某类消息（图片 <img>、表情 <emoji>）的构造/解析代码。
比 r2 的 axt 可靠 —— 全程字节级 + capstone 语义，不依赖 r2 对这份 179MB PE 的寻址。

用法:
    python str_xref.py emoji "<emoji" emoticonmd5
"""
from __future__ import annotations

import bisect
import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
RIP_MODRM = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D}
MAX_REFS_PER_STR = 40


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    needles = [a.encode("utf-8") for a in sys.argv[1:]]
    if not needles:
        print(__doc__)
        return 1

    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    secs = [(s.Name.rstrip(b"\0").decode("ascii", "replace"), s.VirtualAddress,
             s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def off_to_rva(off):
        for name, va, vsz, rp, rs in secs:
            if rp <= off < rp + rs:
                return name, va + (off - rp)
        return None, None

    def rva_to_off(rva):
        for name, va, vsz, rp, rs in secs:
            if va <= rva < va + max(vsz, rs):
                o = rp + (rva - va)
                if o < rp + rs:
                    return o
        return None

    # .pdata 函数边界
    starts, ends = [], []
    for sec in pe.sections:
        if sec.Name.rstrip(b"\0").decode("ascii", "replace") != ".pdata":
            continue
        raw = sec.get_data()
        for i in range(0, len(raw) - 11, 12):
            b = int.from_bytes(raw[i:i + 4], "little")
            e = int.from_bytes(raw[i + 4:i + 8], "little")
            if b and e > b:
                starts.append(b)
                ends.append(e)
        break
    order = sorted(range(len(starts)), key=lambda i: starts[i])
    starts = [starts[i] for i in order]
    ends = [ends[i] for i in order]

    def fn_of(r):
        i = bisect.bisect_right(starts, r) - 1
        if i >= 0 and starts[i] <= r < ends[i]:
            return starts[i], ends[i]
        return None

    # 字符串本体位置
    print("=== 字符串位置 ===")
    str_rvas = {}
    for nd in needles:
        label = nd.decode("utf-8", "replace")
        found = []
        start = 0
        while True:
            pos = data.find(nd, start)
            if pos < 0:
                break
            sec, rva = off_to_rva(pos)
            if rva is not None:
                found.append((pos, rva, sec))
            start = pos + 1
            if len(found) > 60:
                break
        if not found:
            print(f"  {label!r:<20} 未找到")
            continue
        for pos, rva, sec in found[:12]:
            tail = data[pos:pos + 60].split(b"\0")[0].decode("utf-8", "replace")
            print(f"  {label!r:<20} rva={rva:#010x} [{sec}] {tail!r}")
            str_rvas.setdefault(rva, label)
        if len(found) > 12:
            print(f"  {label!r:<20} ... 共 {len(found)} 处")

    if not str_rvas:
        return 1

    # 扫 .text 找 lea 引用
    text = next((s for s in secs if s[0] == ".text"), None)
    if not text:
        raise SystemExit("找不到 .text")
    _n, tva, tvsz, trp, trs = text
    body = data[trp:trp + min(tvsz, trs)]

    print("\n=== 引用这些字符串的 lea（按所属函数汇总）===")
    by_fn = {}
    i = 0
    n = len(body)
    while i < n - 7:
        b0 = body[i]
        if b0 in (0x48, 0x4C) and body[i + 1] == 0x8D and body[i + 2] in RIP_MODRM:
            disp = struct.unpack_from("<i", body, i + 3)[0]
            instr = tva + i
            tgt = instr + 7 + disp
            if tgt in str_rvas:
                fn = fn_of(instr)
                key = fn[0] if fn else instr
                by_fn.setdefault(key, {"fn": fn, "refs": []})
                by_fn[key]["refs"].append((instr, str_rvas[tgt]))
            i += 7
            continue
        i += 1

    for fstart, info in sorted(by_fn.items()):
        fn = info["fn"]
        strs = sorted({s for _a, s in info["refs"]})
        fdesc = f"[{fn[0]:#010x},{fn[1]:#010x}) size={fn[1]-fn[0]}" if fn else "(无 pdata)"
        print(f"\n  fn {fdesc}")
        print(f"    引用 {len(info['refs'])} 处，涉及字符串: {strs}")
        for instr, s in info["refs"][:14]:
            print(f"      instr={instr:#010x}  -> {s!r}")
        if len(info["refs"]) > 14:
            print(f"      ... 还有 {len(info['refs'])-14} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
