"""解析 DoAddMsg 的 trampoline（VirtualAlloc 分配的匿名内存，不属于任何模块）。

预期结构（来自 receive.c 的 build_trampoline）：
    pushfq / push 寄存器          <- 保存现场
    sub rsp, <大缓冲区>           <- process_message 用的栈空间
    mov rcx, <msg_base>
    call <process_message>        <- 应在 hook DLL 内
    恢复寄存器
    jmp <DoAddMsg + N>            <- 应回到 Weixin.dll
"""
import ctypes
import sys
from ctypes import wintypes

pid = int(sys.argv[1])
tramp = int(sys.argv[2], 16)
hook_base = int(sys.argv[3], 16)
weixin_base = int(sys.argv[4], 16)
WEIXIN_SIZE = 0x0C000000

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


print(f"trampoline @ {tramp:#x}")
print(f"hook dll   @ {hook_base:#x} .. {hook_base + 0x40000:#x}")
print(f"weixin dll @ {weixin_base:#x}")

code = rd(tramp, 256)
if not code:
    print("READ FAIL")
    sys.exit(1)

print("\n--- disassembly-ish dump ---")
for i in range(0, 128, 16):
    print(f"  +{i:02x}: {' '.join(f'{x:02X}' for x in code[i:i+16])}")

print("\n--- decode key instructions ---")
# pushfq / pushes
i = 0
saved = []
while i < len(code):
    b = code[i]
    if b == 0x9C:
        saved.append("pushfq")
        i += 1
    elif b == 0x50:
        saved.append("rax")
        i += 1
    elif b == 0x51:
        saved.append("rcx")
        i += 1
    elif b == 0x52:
        saved.append("rdx")
        i += 1
    elif b == 0x53:
        saved.append("rbx")
        i += 1
    elif b == 0x41 and i + 1 < len(code) and code[i + 1] in (0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57):
        saved.append({0x50: "r8", 0x51: "r9", 0x52: "r10", 0x53: "r11",
                      0x54: "r12", 0x55: "r13", 0x56: "r14", 0x57: "r15"}[code[i + 1]])
        i += 2
    else:
        break
print(f"  prologue saves: {', '.join(saved)}")

# 找 sub rsp, imm32  (48 81 EC xx xx xx xx)
for i in range(len(code) - 7):
    if code[i] == 0x48 and code[i + 1] == 0x81 and code[i + 2] == 0xEC:
        imm = int.from_bytes(code[i + 3:i + 7], "little")
        print(f"  +{i:#x}: sub rsp, {imm:#x}  ({imm:,} bytes stack)")
        break

# 找 call rel32 (E8) 和 jmp rel32 (E9)，判断目标落在哪个模块
print("\n--- call/jmp targets ---")
hits = 0
for i in range(len(code) - 5):
    op = code[i]
    if op in (0xE8, 0xE9):
        rel = int.from_bytes(code[i + 1:i + 5], "little", signed=True)
        tgt = tramp + i + 5 + rel
        where = None
        if hook_base <= tgt < hook_base + 0x40000:
            where = "HOOK_DLL"
        elif weixin_base <= tgt < weixin_base + WEIXIN_SIZE:
            where = f"WEIXIN_DLL (DoAddMsg{tgt - weixin_base - 0x166A6BF:+#x})"
        if where:
            kind = "call" if op == 0xE8 else "jmp "
            print(f"  +{i:#x}: {kind} -> {tgt:#x}  [{where}]")
            hits += 1
if not hits:
    print("  (none resolved inside known modules)")

k32.CloseHandle(h)
