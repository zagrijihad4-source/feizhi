# -*- coding: utf-8 -*-
"""微信窗口可见性精查 + 关掉挡路的模态框。

要回答两个问题：
  1. 1510462 到底可见吗？最小化吗？在第几个虚拟桌面？
  2. 谁在挡着前台（模态对话框会锁住前台，微信就永远抢不上来）
"""
import ctypes
import ctypes.wintypes as wt
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

VK_ESCAPE = 0x1B
KEYUP = 0x0002


def probe(hwnd: int, tag: str) -> None:
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    n = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, cls, 256)
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    print("%s hwnd=%d title=%r class=%r pid=%d" % (tag, hwnd, buf.value, cls.value, pid.value))
    print("   visible=%s iconic=%s zoomed=%s enabled=%s rect=(%d,%d)-(%d,%d) %dx%d"
          % (bool(u32.IsWindowVisible(hwnd)), bool(u32.IsIconic(hwnd)),
             bool(u32.IsZoomed(hwnd)), bool(u32.IsWindowEnabled(hwnd)),
             r.left, r.top, r.right, r.bottom,
             r.right - r.left, r.bottom - r.top))
    print("   hosters:", u32.GetWindow(hwnd, 3), " owner:", u32.GetWindow(hwnd, 4))


def main() -> int:
    wx = int(u32.FindWindowW(None, "微信") or 0)
    print("=" * 80)
    probe(wx, "[微信]")
    fg = int(u32.GetForegroundWindow() or 0)
    probe(fg, "[前台]")
    print("=" * 80)

    # 清掉可能存在的模态框：先给前台发 Esc，再试微信主窗
    print("按 Esc 清前台模态框…")
    u32.keybd_event(VK_ESCAPE, 0, 0, None)
    time.sleep(0.05)
    u32.keybd_event(VK_ESCAPE, 0, KEYUP, None)
    time.sleep(0.8)
    probe(int(u32.GetForegroundWindow() or 0), "[Esc 后前台]")

    # 把微信拉起来
    print("=" * 80)
    print("还原并抢前台…")
    if u32.IsIconic(wx):
        u32.ShowWindow(wx, 9)
        time.sleep(0.5)
    u32.ShowWindow(wx, 5)          # SW_SHOW
    ok = bool(u32.SetForegroundWindow(wx))
    time.sleep(0.6)
    print("SetForegroundWindow ->", ok)
    probe(int(u32.GetForegroundWindow() or 0), "[抢完后前台]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
