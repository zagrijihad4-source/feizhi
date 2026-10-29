# -*- coding: utf-8 -*-
"""图片 AES key 的**多形态**扫描器。

上一版只试了「16/32 位可打印 ASCII 原样作 key」，漏了三种常见形态：
  1. 32 个 hex 字符 → bytes.fromhex() 得到 16 字节二进制 key
  2. 16 个 hex 字符 → bytes.fromhex() 得到 8 字节（不够，跳过）
  3. 完全不可打印的 16 字节二进制 key（只能按窗口暴力）

判定用**已知明文-密文对**（原图前 16 字节 vs dat 的 AES 段首块），
比"看魔数"严格得多。

用法:
    python find_img_key2.py            # 字符串形态 + hex 形态
    python find_img_key2.py --window   # 追加 16 字节滑动窗口暴力（慢）
"""
from __future__ import annotations

import re
import sys
import time
import ctypes
import hashlib
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import img_dat as M  # noqa: E402

# 已知明文来源：我们自己发出去的原图
KNOWN_SRC = Path(r"<PROJECT_ROOT>\feizhi_pc\images\gen_9f816f698803f168.jpg")
KNOWN_DAT = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\msg\attach"
                 r"\9e20f478899dc29eb19741386f9343c8\2026-10\Img"
                 r"\9e93939518f3d1932c4351236304064b_h.dat")

RE_STR16 = re.compile(rb"[\x21-\x7e]{16}")
RE_STR32 = re.compile(rb"[\x21-\x7e]{32}")
RE_HEX32 = re.compile(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")

PAGE_NOACCESS, PAGE_GUARD, MEM_COMMIT = 0x01, 0x100, 0x1000
READ_OK = 0x02 | 0x04 | 0x08 | 0x10 | 0x20 | 0x40 | 0x80 | 0x200


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


def plain_cipher_pair() -> tuple[bytes, bytes]:
    src = KNOWN_SRC.read_bytes()[:16]
    dat = KNOWN_DAT.read_bytes()
    return src, dat[15:31]


def check(key: bytes, plain: bytes) -> bool:
    """key 正确时，AES 段解出的首块应等于已知明文。"""
    if len(key) != 16:
        return False
    try:
        from Crypto.Cipher import AES
        dec = AES.new(key, AES.MODE_ECB).decrypt(P_CIPHER)
    except Exception:
        return False
    return dec == P_PLAIN or M.sniff(dec + b"\x00" * 8) is not None


def regions(h):
    addr, out, mbi = 0, [], MBI()
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


def read_region(h, base, size) -> bytes | None:
    if size > 128 * 1024 * 1024:
        return None
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size,
                                 ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def scan_pid(pid: int, with_window: bool) -> tuple[bytes, str] | None:
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        return None
    t0 = time.time()
    n_str = n_hex = n_win = 0
    try:
        regs = regions(h)
        total = sum(r[1] for r in regs)
        print("  PID %d: %d 区域 / %.0f MB" % (pid, len(regs), total / 1048576),
              flush=True)
        for idx, (base, size, prot) in enumerate(regs):
            data = read_region(h, base, size)
            if not data:
                continue
            for m in RE_STR16.finditer(data):
                n_str += 1
                if check(m.group(), P_PLAIN):
                    return m.group(), "ascii16"
            for m in RE_STR32.finditer(data):
                g = m.group()
                n_str += 1
                if check(g[:16], P_PLAIN):
                    return g[:16], "ascii32-head"
                if check(g, P_PLAIN):
                    return g, "ascii32"
            for m in RE_HEX32.finditer(data):
                n_hex += 1
                try:
                    kb = bytes.fromhex(m.group().decode())
                except ValueError:
                    continue
                if check(kb, P_PLAIN):
                    return kb, "hex32->bin16"
            if with_window and (prot & 0x04):  # 仅 RW 区做窗口暴力
                step = 1
                for off in range(0, len(data) - 16, step):
                    n_win += 1
                    if check(data[off:off + 16], P_PLAIN):
                        return data[off:off + 16], "raw-window@%#x" % (base + off)
            if idx % 40 == 0:
                print("    %d/%d %.1fs str=%d hex=%d win=%d"
                      % (idx, len(regs), time.time() - t0, n_str, n_hex, n_win),
                      end="\r", flush=True)
        print("\n  完成 %.1fs: str=%d hex=%d win=%d"
              % (time.time() - t0, n_str, n_hex, n_win), flush=True)
    finally:
        k32.CloseHandle(h)
    return None


def main() -> int:
    global P_PLAIN, P_CIPHER
    P_PLAIN, P_CIPHER = plain_cipher_pair()
    print("已知明文:", P_PLAIN.hex())
    print("对应密文:", P_CIPHER.hex())
    with_window = "--window" in sys.argv
    for pid in M._wechat_pids():
        r = scan_pid(pid, with_window)
        if r:
            key, how = r
            print("\n*** KEY %r (%s) ***" % (key, how))
            M.STATE_DIR.mkdir(parents=True, exist_ok=True)
            M.KEY_FILE.write_text(
                '{"aes_key_hex": "%s", "how": "%s", "pid": %d}'
                % (key.hex(), how, pid), encoding="utf-8")
            print("已写入", M.KEY_FILE)
            return 0
    print("未命中")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
