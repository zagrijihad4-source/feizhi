"""dump 指定 RVA 附近的 vtable 槽位，并把每个函数指针解析成 RVA + 函数大小。

用于看清一个类有哪些虚方法（比如图片消息体除了 GetXml 之外是否有 Upload/Send）。
"""
from __future__ import annotations

import bisect
import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rva = int(sys.argv[1], 16)
    before = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    after = int(sys.argv[3]) if len(sys.argv) > 3 else 16

    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    secs = [(s.Name.rstrip(b"\0").decode("ascii", "replace"), s.VirtualAddress,
             s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

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

    def rva_to_off(r):
        for name, va, vsz, rp, rs in secs:
            if va <= r < va + max(vsz, rs):
                o = rp + (r - va)
                if o < rp + rs:
                    return o
        return None

    print(f"vtable @ rva {rva:#x}，展示前 {before} / 后 {after} 个槽位\n")
    for k in range(-before, after + 1):
        slot_rva = rva + k * 8
        off = rva_to_off(slot_rva)
        if off is None or off + 8 > len(data):
            continue
        ptr = struct.unpack_from("<Q", data, off)[0]
        marker = "  <== 目标槽位" if k == 0 else ""
        if ptr == 0:
            print(f"  [{k:+3d}] rva={slot_rva:#010x}  (null){marker}")
            continue
        if ptr >= IMAGE_BASE:
            trva = ptr - IMAGE_BASE
            f = fn_of(trva)
            fs = f"fn [{f[0]:#x},{f[1]:#x}) size={f[1]-f[0]}" if f else "不在 .pdata 函数内"
            print(f"  [{k:+3d}] rva={slot_rva:#010x}  ptr={ptr:#012x} -> rva {trva:#010x}  {fs}{marker}")
        else:
            print(f"  [{k:+3d}] rva={slot_rva:#010x}  ptr={ptr:#012x}  (非函数指针){marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
