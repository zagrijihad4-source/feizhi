"""在 DLL 已加载但 worker 退出的情况下，重新启动远程 worker 线程。

背景（2026-10-19 事故）：微信崩溃重启后，DLL 在我们注入时还停在登录窗口，
worker 绑到那个窗口，登录窗口一销毁 worker 就自己退了（phase=worker_exiting /
hooked=0 / status=worker stopped）。DLL 还在进程里，但 LoadLibrary 不能重复调用，
reinject.py 看到 "hook already loaded" 就直接返回了。
这里绕过那个检查，直接走 inject_hook —— 它会 GetProcAddress(WxBridgeWorker)
再 CreateRemoteThread，等于在已加载的 DLL 里起一个新 worker。
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\wx-basic-bridge")
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "python" / "inject"))
os.environ.setdefault("WX_HOOK_DLL_FILE", str(ROOT / "dist" / "wx_hook_bridge.dll"))

from wechat_inject import inject_hook  # noqa: E402


def find_main_window() -> tuple[int, int, int]:
    """返回 (pid, hwnd, tid)：可见、最大、Qt 前缀的微信窗口。"""
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    found: list[tuple[int, int, int, int]] = []
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u32.EnumWindows.argtypes = [CB, wintypes.LPARAM]
    u32.EnumWindows.restype = wintypes.BOOL

    def _cb(hwnd, _lp):
        if not u32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        if not cls.value.startswith("Qt"):
            return True
        title = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(hwnd, title, 512)
        if "微信" not in title:
            return True
        pid = wintypes.DWORD()
        tid = u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        r = wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        found.append((area, int(pid.value), int(hwnd), int(tid)))
        return True

    u32.EnumWindows(CB(_cb), 0)
    if not found:
        raise SystemExit("找不到微信主窗口")
    found.sort(reverse=True)
    area, pid, hwnd, tid = found[0]
    print("main window: pid=%d hwnd=%d tid=%d area=%d" % (pid, hwnd, tid, area))
    return pid, hwnd, tid


if __name__ == "__main__":
    # 允许直接给 hwnd（窗口枚举在某些环境下拿不到，用已知句柄更可靠）
    if len(sys.argv) > 1:
        hwnd = int(sys.argv[1], 0)
        pid = wintypes.DWORD()
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        tid = u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        print("given hwnd=%d -> pid=%d tid=%d" % (hwnd, pid.value, tid))
        pid = int(pid.value)
    else:
        pid, hwnd, tid = find_main_window()
    # 清掉可能残留的 stop.txt（worker 主循环第一件事就是看它）
    (ROOT / "bridge" / "control" / "stop.txt").unlink(missing_ok=True)
    rc = inject_hook(pid, tid, hwnd)
    print("inject_hook rc =", rc)
    sys.exit(rc)
