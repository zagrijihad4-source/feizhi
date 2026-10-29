"""验证 hook 的 trampoline 是否被正确构建。

hook 安装流程（receive.c）：
  1. alloc_near(target) 在 DoAddMsg 附近分配 TRAMPOLINE_SIZE(256) 字节
  2. build_trampoline() 写入: 保存寄存器 -> call process_message -> 恢复 -> jmp 回 DoAddMsg+N
  3. DoAddMsg 入口被改写为 E9 <rel> 跳到 trampoline 起始

本脚本读 DLL 基址处的字节，看 trampoline 是否真在那里，并解析出它跳回哪里。
"""
import ctypes
import sys
from ctypes import wintypes

pid = int(sys.argv[1])
hook_base = int(sys.argv[2], 16)
weixin_base = int(sys.argv[3], 16)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
]
k32.CloseHandle.argtypes = [wintypes.HANDLE]

h = k32.OpenProcess(0x0410, False, pid)
if not h:
    print("OpenProcess failed")
    sys.exit(1)


def rd(addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[: got.value] if ok else None


print(f"pid={pid}")
print(f"hook_dll_base   = {hook_base:#x}")
print(f"weixin_dll_base = {weixin_base:#x}")

# 1) DoAddMsg 入口
do_add = weixin_base + 0x166A6BF
b = rd(do_add, 8)
print(f"\n[1] DoAddMsg entry {do_add:#x}: {' '.join(f'{x:02X}' for x in b)}")
if b[0] == 0xE9:
    rel = int.from_bytes(b[1:5], "little", signed=True)
    tgt = do_add + 5 + rel
    print(f"    E9 rel={rel:#x} -> target={tgt:#x}")
    print(f"    target == hook base? {tgt == hook_base}")
else:
    print("    not patched!")

# 2) trampoline 内容（在 hook DLL 基址）
tramp = rd(hook_base, 64)
print(f"\n[2] hook_base first 64 bytes:")
if tramp:
    for i in range(0, 64, 16):
        print(f"    +{i:02x}: {' '.join(f'{x:02X}' for x in tramp[i:i+16])}")
else:
    print("    READ FAIL")

# 3) 扫描 trampoline 里是否有跳回 DoAddMsg 区域的 jmp (E9/E8 后接指向 Weixin.dll 的偏移)
if tramp:
    print("\n[3] scanning for jumps back into Weixin.dll range:")
    found = 0
    for i in range(len(tramp) - 5):
        if tramp[i] in (0xE9, 0xE8):
            rel = int.from_bytes(tramp[i + 1:i + 5], "little", signed=True)
            tgt = hook_base + i + 5 + rel
            if weixin_base <= tgt < weixin_base + 0x0C000000:
                kind = "jmp" if tramp[i] == 0xE9 else "call"
                print(f"    +{i:#x}: {kind} -> {tgt:#x} "
                      f"(DoAddMsg+{tgt - weixin_base - 0x166A6BF:#x})")
                found += 1
    if not found:
        print("    none found in first 64 bytes (trampoline may be longer)")

# 4) 扫更大范围
big = rd(hook_base, 1024)
if big:
    print("\n[4] scanning first 1024 bytes for jumps back to Weixin:")
    for i in range(len(big) - 5):
        if big[i] == 0xE9:
            rel = int.from_bytes(big[i + 1:i + 5], "little", signed=True)
            tgt = hook_base + i + 5 + rel
            if weixin_base <= tgt < weixin_base + 0x0C000000:
                off = tgt - weixin_base - 0x166A6BF
                print(f"    +{i:#x}: jmp -> {tgt:#x} (DoAddMsg{off:+#x})")

k32.CloseHandle(h)
