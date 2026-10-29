# -*- coding: utf-8 -*-
"""第三版 key 扫描：覆盖 UTF-16LE 编码的 key。

之前漏掉的形态（Windows 微信大量使用 UTF-16 字符串）：
    'a1b2c3d4e5f6g7h8'  →  'a\\0 1\\0 b\\0 …'  单字节正则匹配不到

同时对 UTF-16 的 32 字符（hex 形态）再 fromhex。

用法:
    python find_img_key3.py
"""
from __future__ import annotations

import ctypes
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import img_dat as M  # noqa: E402

KNOWN_SRC = Path(r"<PROJECT_ROOT>\feizhi_pc\images\gen_9f816f698803f168.jpg")
KNOWN_DAT = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\msg\attach"
                 r"\9e20f478899dc29eb19741386f9343c8\2026-10\Img"
                 r"\9e93939518f3d1932c4351236304064b_h.dat")

# UTF-16LE 的可打印串：每个字符后跟 \x00
RE_U16_16 = re.compile(rb"(?:[\x21-\x7e]\x00){16}")
RE_U16_32 = re.compile(rb"(?:[\x21-\x7e]\x00){32}")
RE_A16 = re.compile(rb"[\x21-\x7e]{16}")
RE_HEX32 = re.compile(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")
RE_U16HEX32 = re.compile(rb"(?:[0-9a-fA-F]\x00){32}")

PAGE_NOACCESS, PAGE_GUARD, MEM_COMMIT = 0x01, 0x100, 0x1000


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


k32 = ctypes.windll.kernel32
PLAIN = KNOWN_SRC.read_bytes()[:16]
CIPHER = KNOWN_DAT.read_bytes()[15:31]


def good(key: bytes) -> bool:
    if len(key) != 16:
        return False
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_ECB).decrypt(CIPHER) == PLAIN
    except Exception:  # noqa: BLE001
        return False


def regions(h):
    addr, out, mbi = 0, [], MBI()
    while addr < 0x7FFFFFFFFFFF:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                  ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.Protect != PAGE_NOACCESS
                and not (mbi.Protect & PAGE_GUARD)):
            out.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = addr + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return out


def scan(pid: int):
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        return None
    t0 = time.time()
    counts = {"u16_16": 0, "u16_32": 0, "a16": 0, "hex": 0, "u16hex": 0}
    try:
        for base, size in regions(h):
            if size > 160 * 1024 * 1024:
                continue
            buf = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t(0)
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size,
                                         ctypes.byref(got)):
                continue
            data = buf.raw[:got.value]

            for m in RE_U16_16.finditer(data):
                counts["u16_16"] += 1
                kb = m.group().replace(b"\x00", b"")
                if good(kb):
                    return kb, "utf16-16"
            for m in RE_U16_32.finditer(data):
                counts["u16_32"] += 1
                kb = m.group().replace(b"\x00", b"")
                if good(kb[:16]):
                    return kb[:16], "utf16-32-head"
                if good(kb):
                    return kb, "utf16-32"
            for m in RE_A16.finditer(data):
                counts["a16"] += 1
                if good(m.group()):
                    return m.group(), "ascii16"
            for m in RE_HEX32.finditer(data):
                counts["hex"] += 1
                try:
                    kb = bytes.fromhex(m.group().decode())
                except ValueError:
                    continue
                if good(kb):
                    return kb, "hex32"
            for m in RE_U16HEX32.finditer(data):
                counts["u16hex"] += 1
                try:
                    kb = bytes.fromhex(m.group().replace(b"\x00", b"").decode())
                except ValueError:
                    continue
                if good(kb):
                    return kb, "utf16-hex32"
        print("  PID %d 完成 %.1fs %s" % (pid, time.time() - t0, counts), flush=True)
    finally:
        k32.CloseHandle(h)
    return None


def main() -> int:
    print("已知明文", PLAIN.hex())
    print("对应密文", CIPHER.hex())
    for pid in M._wechat_pids():
        r = scan(pid)
        if r:
            key, how = r
            print("\n*** KEY %r (%s) ***" % (key, how))
            M.STATE_DIR.mkdir(parents=True, exist_ok=True)
            M.KEY_FILE.write_text(
                '{"aes_key_hex": "%s", "how": "%s"}' % (key.hex(), how),
                encoding="utf-8")
            print("已写入", M.KEY_FILE)
            return 0
    print("未命中")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
