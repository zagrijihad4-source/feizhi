"""Read Weixin.exe process memory to verify the DoAddMsg inline hook is installed."""
import ctypes
import sys
from ctypes import wintypes

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
]
k32.CloseHandle.argtypes = [wintypes.HANDLE]

SIZE = 0x1801_0000
OFF_DOADDMSG = 0x166A6BF
OFF_SEND_CALL1 = 0x6A35B0
OFF_SEND_CALL3 = 0x160EBE0

pid = int(sys.argv[1])
base = int(sys.argv[2], 16)
h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    print(f"OpenProcess failed: {ctypes.get_last_error()}")
    sys.exit(1)


def read(addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[: got.value] if ok else None


def hexs(b):
    return " ".join(f"{x:02X}" for x in b)


print(f"pid={pid} base={base:#x}")
for name, off in (
    ("DOADDMSG", OFF_DOADDMSG),
    ("SEND_CALL1", OFF_SEND_CALL1),
    ("SEND_CALL3", OFF_SEND_CALL3),
):
    addr = base + off
    b = read(addr, 16)
    print(f"{name:11s} @{addr:#x} (rva {off:#x}): {hexs(b) if b else 'READ FAIL'}")

# look for a jump / patched prologue near DOADDMSG (hook usually patches the head)
print("\n--- scan 64 bytes at DOADDMSG entry ---")
b = read(base + OFF_DOADDMSG, 64)
if b:
    print(hexs(b))
    print("first byte:", f"{b[0]:02X}",
          "-> E9/EB/FF = jump, 68 = push" if b[0] in (0xE9, 0xEB, 0xFF, 0x68) else "-> not a jmp")

k32.CloseHandle(h)
