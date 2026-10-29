# -*- coding: utf-8 -*-
"""枚举所有顶层窗口，找出「微信」到底是哪个 hwnd，顺带看清谁盖着谁。"""
import ctypes
import ctypes.wintypes as wt

u32 = ctypes.windll.user32

EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def main() -> int:
    rows = []

    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        r = wt.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rows.append((hwnd, buf.value, cls.value, r, pid.value))
        return True

    u32.EnumWindows(EnumProc(cb), 0)

    print("=" * 100)
    print("按 z 序（前台在最前）:")
    for hwnd, title, cls, r, pid in rows:
        print("%-10d pid=%-7d %-26s %4dx%-4d @%-5d,%-5d  %s"
              % (hwnd, pid, cls[:26], r.right - r.left, r.bottom - r.top,
                 r.left, r.top, title[:50]))
    print("=" * 100)
    fg = int(u32.GetForegroundWindow() or 0)
    print("前台 hwnd =", fg)
    print("FindWindowW(None,'微信') =", int(u32.FindWindowW(None, "微信") or 0))
    for hwnd, title, cls, r, pid in rows:
        if "微信" in title or "Weixin" in cls or "WeChat" in cls or "Qt" in cls:
            print("  >> 候选 %d pid=%d title=%r class=%r size=%dx%d"
                  % (hwnd, pid, title, cls, r.right - r.left, r.bottom - r.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
