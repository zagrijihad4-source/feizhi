# -*- coding: utf-8 -*-
"""验证「搜索框定位会话」这条路能不能走通。

语音发不出去的真凶是：微信停在「腾讯新闻」公众号会话里，那里没有输入框
也没有「按住说话」按钮，Alt 投下去 Encode 一次都不会调（calls=0）。
而 open_recent_chat() 点的是"会话列表第一行"，公众号一推送就把第一行占了。

这里验证能不能用搜索框精确定位到指定联系人：
  1. 点搜索框
  2. PostMessage WM_CHAR 逐字输入备注名（微信是 CEF，实测 WM_CHAR 有效）
  3. 截图看搜索结果，再点第一条
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
WM_CHAR = 0x0102


def shot(hwnd: int, name: str) -> Path:
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = max(r.left, 0), max(r.top, 0)
    w, h = r.right - r.left, r.bottom - r.top
    out = Path(__file__).parent / "state" / name
    ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
          "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
          "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height);"
          "$g=[System.Drawing.Graphics]::FromImage($bmp);"
          "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
          "$r=New-Object System.Drawing.Rectangle(%d,%d,%d,%d);"
          "$c=$bmp.Clone($r,$bmp.PixelFormat);"
          "$c.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png);"
          "$c.Dispose();$g.Dispose();$bmp.Dispose()" % (x, y, w, h, str(out)))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=90)
    return out


def click(x: int, y: int, hold: float = 0.09) -> None:
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(hold)
    u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.25)


def main() -> int:
    import voice

    hwnd = voice.find_wechat_window()
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    dpi = u32.GetDpiForWindow(hwnd) or 96
    s = dpi / 96.0
    print("窗口 rect=(%d,%d)-(%d,%d) DPI=%d 缩放=%.2f"
          % (r.left, r.top, r.right, r.bottom, dpi, s))

    u32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

    # 搜索框：截图量出来在窗口内约 (150~400, 90~125) 物理像素 → 中心 (225, 57)
    # 按 DIP 记：中心约 (150, 38) DIP
    sx = r.left + int(150 * s)
    sy = r.top + int(38 * s)
    print("点搜索框屏幕坐标 (%d,%d)" % (sx, sy))
    click(sx, sy)
    print("已点搜索框 ->", shot(hwnd, "_wx_s1_search.png"))

    # 逐字输入备注名
    for ch in "<OWNER>":
        u32.PostMessageW(hwnd, WM_CHAR, ctypes.c_void_p(ord(ch)), ctypes.c_void_p(1))
        time.sleep(0.12)
    time.sleep(1.2)
    print("已输入「<OWNER>」->", shot(hwnd, "_wx_s2_typed.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
