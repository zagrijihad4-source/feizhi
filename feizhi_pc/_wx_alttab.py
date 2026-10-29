# -*- coding: utf-8 -*-
"""试 Alt+Tab 和 Alt+Esc，走系统窗口切换，逼 Qt 收到真正的 activate 事件。

Win32 的 ShowWindow / SetForegroundWindow 已经被证明叫不醒它（白 98.7%）。
Alt+Tab 是用户真会做的动作，底层会发 WM_SYSCOMMAND / WM_ACTIVATE，
Qt 只有收到这些才会认为"我真的被显示出来了"并重新布局。
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

VK_MENU, VK_TAB = 0x12, 0x09
KEYUP = 0x0002


def white(tag: str) -> float:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    w, h, px = pw.grab(hwnd)
    if not px:
        print("  %-12s 拿不到内容" % tag)
        return -1.0
    total = white_n = 0
    for i in range(0, len(px) - 3, 44):
        b, g, r = px[i], px[i + 1], px[i + 2]
        total += 1
        if r > 235 and g > 235 and b > 235:
            white_n += 1
    v = 100.0 * white_n / total
    print("  %-12s %dx%d 白 %.1f%%  可见=%s" % (tag, w, h, v,
                                                bool(u32.IsWindowVisible(hwnd))))
    return v


def alt_tab() -> None:
    u32.keybd_event(VK_MENU, 0, 0, None)
    time.sleep(0.06)
    u32.keybd_event(VK_TAB, 0, 0, None)
    time.sleep(0.12)
    u32.keybd_event(VK_TAB, 0, KEYUP, None)
    time.sleep(0.06)
    u32.keybd_event(VK_MENU, 0, KEYUP, None)


def main() -> int:
    print("先看初始：")
    white("初始")

    # 把微信藏起来再让 Alt+Tab 找回它，走完整状态机
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    print("最小化微信，然后用 Alt+Tab 切回来…")
    u32.ShowWindow(hwnd, 6)
    time.sleep(0.8)
    for i in range(2):
        alt_tab()
        time.sleep(1.0)
        print("Alt+Tab 第 %d 次后，前台 hwnd=%d"
              % (i + 1, int(u32.GetForegroundWindow() or 0)))
        white("Alt+Tab %d" % (i + 1))
        if int(u32.GetForegroundWindow() or 0) == hwnd:
            break
        time.sleep(0.5)

    time.sleep(1.5)
    print("再等 1.5s：")
    white("最终")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
