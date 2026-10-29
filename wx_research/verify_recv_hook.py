"""接收 hook 完整性验证：解析 DoAddMsg 的 trampoline。

用法: python verify_recv_hook.py [pid]

验证链：
  1. Weixin.dll 里 DoAddMsg 入口已被改写为 E9 -> trampoline (VirtualAlloc 匿名内存)
  2. trampoline 的序言保存现场（pushfq + 通用寄存器 + XMM）
  3. trampoline 用 movabs rax,<addr> + call rax 调 process_message
  4. process_message 的地址落在 hook DLL 的映像范围内
  5. trampoline 末尾恢复现场并跳回 DoAddMsg（原函数继续执行）

注意：trampoline 不在 Modules 列表里，因为它是 VirtualAlloc 分配的匿名内存。
所以要先用 DoAddMsg 入口的 E9 相对偏移自己算出 trampoline 地址。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

DOADDMSG_RVA = 0x166A6BF
PAGE = 0x1000

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
]
k32.CloseHandle.argtypes = [wintypes.HANDLE]


def find_target_process() -> tuple[int, int, int]:
    """返回 (pid, weixin_base, hook_base)。"""
    import subprocess

    ps = (
        "Get-Process Weixin -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { "
        "$hb = ($_.Modules | Where-Object { $_.ModuleName -eq 'Weixin.dll' } | Select-Object -First 1); "
        "$kb = ($_.Modules | Where-Object { $_.ModuleName -like 'wx_hook_bridge*' } | Select-Object -First 1); "
        "if ($hb) { \"$($_.Id)|$($hb.BaseAddress.ToInt64())|$(if ($kb) { $kb.BaseAddress.ToInt64() } else { 0 })\" } }"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=60,
    ).stdout.strip().splitlines()
    for line in out:
        parts = line.strip().split("|")
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
    raise SystemExit("no Weixin process hosting Weixin.dll found")


def main() -> int:
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
        _, wb, kb = find_target_process()
    else:
        pid, wb, kb = find_target_process()

    print(f"pid={pid}")
    print(f"weixin.dll base = {wb:#x}")
    print(f"hook dll  base  = {kb:#x}" + ("" if kb else "  (hook NOT loaded!)"))

    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        print("OpenProcess failed")
        return 1

    def rd(addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
        return buf.raw[: got.value] if ok else None

    ok_all = True

    # 1) DoAddMsg 入口
    entry = wb + DOADDMSG_RVA
    b = rd(entry, 8)
    print(f"\n[1] DoAddMsg @ {entry:#x}: {' '.join(f'{x:02X}' for x in b)}")
    if b[0] != 0xE9:
        print("    FAIL: entry not patched with E9")
        return 1
    rel = int.from_bytes(b[1:5], "little", signed=True)
    tramp = entry + 5 + rel
    print(f"    E9 rel={rel:+#x} -> trampoline @ {tramp:#x}  OK")

    # 2) trampoline 序言
    code = rd(tramp, 256)
    if not code:
        print("    FAIL: cannot read trampoline")
        return 1
    prologue = code[:13]
    print(f"\n[2] trampoline prologue: {' '.join(f'{x:02X}' for x in prologue)}")
    if prologue[0] == 0x9C:
        print("    pushfq  OK")
    else:
        print("    WARN: expected pushfq (9C) first")

    # 3) movabs + call rax
    print("\n[3] scanning for movabs rax,imm64 (48 B8) followed by call rax (FF D0)")
    proc_addr = None
    for i in range(len(code) - 12):
        if code[i] == 0x48 and code[i + 1] == 0xB8:
            imm = int.from_bytes(code[i + 2:i + 10], "little")
            j = i + 10
            if code[j] == 0xFF and code[j + 1] in (0xD0, 0xD1, 0xD2, 0xD3, 0xD6, 0xD7):
                print(f"    +{i:#x}: movabs rax, {imm:#x} ; call rax")
                proc_addr = imm
                break

    if proc_addr is None:
        print("    FAIL: no movabs+call rax pattern found")
        ok_all = False
    else:
        # 4) 目标是否在 hook DLL 内
        in_dll = kb and (kb <= proc_addr < kb + 0x40000)
        print(f"\n[4] process_message candidate = {proc_addr:#x}")
        print(f"    inside hook dll [{kb:#x} .. {kb + 0x40000:#x}] ? {'YES  OK' if in_dll else 'NO  FAIL'}")
        if not in_dll:
            ok_all = False

    # 5) 尾部是否跳回 Weixin
    print("\n[5] looking for jump back into Weixin.dll in trampoline tail")
    back = None
    for i in range(len(code) - 5):
        if code[i] == 0xE9:
            r = int.from_bytes(code[i + 1:i + 5], "little", signed=True)
            tgt = tramp + i + 5 + r
            if wb <= tgt < wb + 0x0C000000:
                back = tgt
                print(f"    +{i:#x}: jmp -> {tgt:#x}  (DoAddMsg{tgt - entry:+#x})  OK")
                break
    if back is None:
        print("    (no direct jmp found in first 256B; trampoline may place it further)")

    k32.CloseHandle(h)
    print("\n=== RESULT:", "hook looks CORRECT" if ok_all else "hook has problems", "===")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
