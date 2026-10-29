# -*- coding: utf-8 -*-
"""在微信所有进程里搜图片 AES key（不设 RW 限制，覆盖 .rdata 硬编码）。

用法:
    python find_img_key.py [--all]   # --all 时扫描所有可读区域（慢）
"""
from __future__ import annotations

import ctypes
import re
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import img_dat as M  # noqa: E402

PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
MEM_COMMIT = 0x1000
READABLE = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80 | 0x10 | 0x200


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


k32 = ctypes.windll.kernel32

RE16 = re.compile(rb"[\x21-\x7e]{16}")
RE32 = re.compile(rb"[\x21-\x7e]{32}")


def try_aes(key: bytes, ct: bytes) -> str | None:
    try:
        from Crypto.Cipher import AES
        dec = AES.new(key, AES.MODE_ECB).decrypt(ct)
    except Exception:
        return None
    ext = M.sniff(dec)
    return ext


def regions_of(h):
    addr = 0
    mbi = MBI()
    out = []
    while addr < 0x7FFFFFFFFFFF:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                  ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.Protect != PAGE_NOACCESS
                and not (mbi.Protect & PAGE_GUARD)):
            out.append((mbi.BaseAddress, mbi.RegionSize, mbi.Protect))
        nxt = addr + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return out


def scan(h, ct, all_regions: bool) -> tuple[bytes, str] | None:
    regs = regions_of(h)
    total = sum(r[1] for r in regs)
    print("  区域 %d 个 / %.0f MB" % (len(regs), total / 1048576), flush=True)
    t0 = time.time()
    cand_n = 0
    for i, (base, size, prot) in enumerate(regs):
        if size > 120 * 1024 * 1024:
            continue
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size,
                                     ctypes.byref(got)):
            continue
        data = buf.raw[:got.value]
        for m in RE16.finditer(data):
            cand_n += 1
            ext = try_aes(m.group(), ct)
            if ext:
                return m.group(), ext
        for m in RE32.finditer(data):
            cand_n += 1
            g = m.group()
            ext = try_aes(g[:16], ct)
            if ext:
                return g[:16], ext
            ext = try_aes(g, ct)
            if ext:
                return g, ext
        if i % 50 == 0:
            print("    %d/%d  %.1fs  候选 %d" % (i, len(regs), time.time() - t0, cand_n),
                  end="\r", flush=True)
    print("\n    扫完 %.1fs，候选 %d 个，无命中" % (time.time() - t0, cand_n), flush=True)
    return None


def main():
    ct = M._sample_ciphertext()
    if ct is None:
        print("找不到 V2 样本密文")
        return 1
    print("样本密文:", ct.hex())
    pids = M._wechat_pids()
    print("微信 PID:", pids)
    access = 0x0010 | 0x0400
    for pid in pids:
        h = k32.OpenProcess(access, False, pid)
        if not h:
            print("PID %d 打不开" % pid)
            continue
        print("\n== PID %d ==" % pid, flush=True)
        try:
            r = scan(h, ct, "--all" in sys.argv)
        finally:
            k32.CloseHandle(h)
        if r:
            key, ext = r
            print("\n*** 找到 KEY: %r -> %s ***" % (key, ext))
            M.STATE_DIR.mkdir(parents=True, exist_ok=True)
            M.KEY_FILE.write_text(
                '{"aes_key": "%s", "pid": %d}' % (key.decode("ascii", "replace"), pid),
                encoding="utf-8")
            print("已写入", M.KEY_FILE)
            return 0
    print("\n全部进程均未命中")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
