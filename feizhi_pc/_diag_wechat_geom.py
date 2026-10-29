"""诊断微信窗口几何，算出「会话列表第一行」的准确屏幕坐标。

`send_voice_robust.py` 用的是 GetWindowRect 的 top + 95，但 95 是**客户区**里的值，
GetWindowRect 给的是**窗口外框**，两者差一个标题栏 + 边框的高度。
差这几十像素就可能点到搜索框、头像或空白处，会话根本没切换 ——
表现就是按住说话按钮不存在，Alt 投出去 calls=0。
"""
import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8")

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.FindWindowW.restype = wintypes.HWND
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
u32.IsIconic.argtypes = [wintypes.HWND]
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.GetForegroundWindow.restype = wintypes.HWND

hwnd = int(u32.FindWindowW(None, "微信") or 0)
print("hwnd =", hwnd)
if not hwnd:
    sys.exit("没找到微信窗口")

print("可见 =", bool(u32.IsWindowVisible(hwnd)), " 最小化 =", bool(u32.IsIconic(hwnd)))

wr = wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(wr))
print("窗口外框: left=%d top=%d right=%d bottom=%d  (%dx%d)"
      % (wr.left, wr.top, wr.right, wr.bottom, wr.right - wr.left, wr.bottom - wr.top))

cr = wintypes.RECT()
u32.GetClientRect(hwnd, ctypes.byref(cr))
print("客户区尺寸: %dx%d" % (cr.right - cr.left, cr.bottom - cr.top))

origin = wintypes.POINT(0, 0)
u32.ClientToScreen(hwnd, ctypes.byref(origin))
print("客户区原点(屏幕): x=%d y=%d" % (origin.x, origin.y))
print("=> 标题栏+边框高度 = %d px" % (origin.y - wr.top))

print()
print("两种点法差多少：")
print("  send_voice_robust 的做法: (%d, %d)" % (wr.left + 200, wr.top + 95))
pt = wintypes.POINT(200, 95)
u32.ClientToScreen(hwnd, ctypes.byref(pt))
print("  客户区(200,95) 转屏幕:     (%d, %d)" % (pt.x, pt.y))
print("  y 方向相差 %d px" % (pt.y - (wr.top + 95)))

fg = int(u32.GetForegroundWindow() or 0)
print()
print("当前前台 hwnd =", fg, " 是微信:", fg == hwnd)
