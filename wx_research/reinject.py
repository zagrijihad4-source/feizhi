"""一次性重注入：找到微信主进程 -> 校验版本 -> 若 hook 未装载则注入 -> 立即退出。

与工程自带的 inject_bridge.py 的区别：后者注入完会进入常驻等待循环（永不退出），
不适合被守护进程同步调用。这里只做注入，做完就退。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\wx-basic-bridge")
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "python" / "inject"))

# 注入器会尝试用工程脚本重建 DLL；我们已经用 clang 编好了，直接指定，避免它去找 vcvars。
os.environ.setdefault("WX_HOOK_DLL_FILE", str(ROOT / "dist" / "wx_hook_bridge.dll"))

from wechat_inject import inject_hook  # noqa: E402
from wechat_native import choose_wechat_target, find_wechat_processes  # noqa: E402

SUPPORTED = "4.1.9.23"
HOOK_PREFIX = "wx_hook_bridge"
INJECT_TIMEOUT = 90.0


def hook_loaded(pid: int) -> bool:
    """检查目标进程是否已加载 hook DLL。"""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010

    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.EnumProcessModules.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    psapi.GetModuleBaseNameW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD,
    ]
    psapi.GetModuleBaseNameW.restype = wintypes.DWORD

    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return False
    try:
        mods = (ctypes.c_void_p * 1024)()
        needed = wintypes.DWORD(0)
        if not psapi.EnumProcessModules(h, mods, ctypes.sizeof(mods), ctypes.byref(needed)):
            return False
        count = min(needed.value // ctypes.sizeof(ctypes.c_void_p), 1024)
        buf = ctypes.create_unicode_buffer(260)
        for i in range(count):
            if psapi.GetModuleBaseNameW(h, mods[i], buf, 260):
                if HOOK_PREFIX in buf.value.lower():
                    return True
        return False
    finally:
        k32.CloseHandle(h)


def main() -> int:
    # 清理上一轮 worker 遗留的状态文件。实测这些文件残留会导致微信下次启动异常退出，
    # 必须在注入前清掉，让本轮 worker 重建。
    for f in ("heartbeat.txt", "status.txt", "worker_owner.txt"):
        p = ROOT / "bridge" / "control" / f
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass

    procs = find_wechat_processes()
    if not procs:
        print("no Weixin process found")
        return 2

    # 只认加载了 Weixin.dll 且版本匹配的主进程
    host = next((p for p in procs if p.get("weixin_base") and p.get("weixin_version") == SUPPORTED), None)
    if not host:
        got = ", ".join(f"{p.get('pid')}:{p.get('weixin_version') or 'n/a'}" for p in procs)
        print(f"no {SUPPORTED} Weixin.dll host yet (candidates: {got})")
        return 3

    pid = int(host["pid"])
    if hook_loaded(pid):
        print(f"hook already loaded in pid={pid}")
        return 0

    target = choose_wechat_target()
    if not target or int(target.get("pid") or 0) == 0:
        print(f"host pid={pid} found but no UI target (window not ready)")
        return 4

    tid = int(target.get("tid") or 0)
    hwnd = int(target.get("hwnd") or 0)
    print(f"injecting: pid={pid} tid={tid} hwnd=0x{hwnd:X} version={host.get('weixin_version')}")

    # inject_hook() 尾部会进入 while True 常驻循环（写 heartbeat 等 stop.txt），
    # 所以放进 daemon 线程跑；主线程轮询目标进程模块列表，一旦 hook 到位立刻硬退出。
    holder: dict = {}

    def worker():
        try:
            holder["rc"] = inject_hook(pid, tid, hwnd)
        except Exception as exc:  # noqa: BLE001
            holder["err"] = repr(exc)

    th = threading.Thread(target=worker, daemon=True)
    th.start()

    deadline = time.time() + INJECT_TIMEOUT
    while time.time() < deadline:
        time.sleep(1.0)
        if hook_loaded(pid):
            print(f"OK hook verified in pid={pid} (host alive)")
            sys.stdout.flush()
            # 硬退出：不要等 daemon 线程，也不要触发 atexit/清理
            os._exit(0)
        if "err" in holder:
            print(f"inject raised: {holder['err']}")
            return 6
        if "rc" in holder and not th.is_alive():
            break

    print(f"inject not verified within {INJECT_TIMEOUT:.0f}s (rc={holder.get('rc')})")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
