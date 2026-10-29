# -*- coding: utf-8 -*-
"""微信窗口内容全白 —— 逐个试标准还原手段，每步都用 PrintWindow 验证。

遮挡已经排除（PrintWindow 拿的是窗口自己的画面，98.7% 白）。
怀疑是 Win32 层 ShowWindow 绕过了 Qt 的状态机，Qt 内部仍认为窗口隐藏，
所以不布局、不绘制。这里按"越来越像用户手动操作"的顺序试：
  1. WM_SYSCOMMAND / SC_RESTORE（任务栏还原菜单走的就是这个）
  2. SwitchToThisWindow（Alt+Tab 的底层调用）
  3. 把窗口尺寸改回隐藏前的 895x657，逼 Qt 重新布局
"""
import ctypes
import ctypes.wintypes as wt
import importlib.util
import sys
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pw", str(Path(__file__).parent / "_wx_printwin.py"))
pw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pw)

u32 = ctypes.windll.user32

WM_SYSCOMMAND = 0x0112
SC_RESTORE = 0xF120
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


def white_ratio(tag: str) -> float:
    w, h, px = pw.grab(int(u32.FindWindowW(None, "微信") or 0))
    if not px:
        print("  %s: 拿不到内容" % tag)
        return -1.0
    total = white = 0
    for i in range(0, len(px) - 3, 44):
        b, g, r = px[i], px[i + 1], px[i + 2]
        total += 1
        if r > 235 and g > 235 and b > 235:
            white += 1
    v = 100.0 * white / total
    print("  %-14s %dx%d 白 %.1f%%" % (tag, w, h, v))
    return v


def main() -> int:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    print("微信 hwnd =", hwnd)
    base = white_ratio("初始")

    print("1) WM_SYSCOMMAND/SC_RESTORE")
    u32.PostMessageW(hwnd, WM_SYSCOMMAND, ctypes.c_void_p(SC_RESTORE), ctypes.c_void_p(0))
    time.sleep(1.2)
    white_ratio("SC_RESTORE")

    print("2) SwitchToThisWindow")
    try:
        u32.SwitchToThisWindow(hwnd, True)
    except Exception as exc:  # noqa: BLE001
        print("  调用失败:", exc)
    time.sleep(1.2)
    white_ratio("SwitchTo")

    print("3) 尺寸改回 895x657")
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    u32.SetWindowPos(hwnd, 0, r.left, r.top, 895, 657,
                     SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(1.5)
    v = white_ratio("895x657")

    print("4) 再放大到 1100x700")
    u32.SetWindowPos(hwnd, 0, r.left, r.top, 1100, 700,
                     SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(1.5)
    white_ratio("1100x700")

    print("结论：初始 %.1f%% -> 最后检查完" % base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
