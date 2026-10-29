# -*- coding: utf-8 -*-
"""微信主窗口 98.7% 白 —— 看看它的子窗口树，找被藏起来的那一层。

Qt 应用的顶层窗口通常只是个壳，真正画内容的是子窗口（hosters 7407438）。
如果某个子窗口被隐藏或者尺寸为 0，主窗口就只剩一片白。
"""
import ctypes
import ctypes.wintypes as wt

u32 = ctypes.windll.user32
EnumChildProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def info(hwnd: int) -> str:
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, cls, 256)
    n = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    return ("hwnd=%-10d %-28s vis=%-5s %4dx%-4d @%-5d,%-5d  %s"
            % (hwnd, cls.value[:28], bool(u32.IsWindowVisible(hwnd)),
               r.right - r.left, r.bottom - r.top, r.left, r.top, buf.value[:30]))


def main() -> int:
    wx = int(u32.FindWindowW(None, "微信") or 0)
    print("主窗口:", info(wx))
    print("-" * 110)
    kids = []

    def cb(hwnd, _):
        kids.append(hwnd)
        return True

    u32.EnumChildWindows(wx, EnumChildProc(cb), 0)
    print("子窗口共 %d 个" % len(kids))
    for h in kids:
        print("  " + info(h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
