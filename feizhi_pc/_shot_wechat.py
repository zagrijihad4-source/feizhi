"""截微信窗口，看清「按住说话」按钮到底存不存在。

用 PrintWindow(PW_RENDERFULLCONTENT=2)，对 Qt+CEF 窗口比 BitBlt 可靠。
"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.FindWindowW.restype = wintypes.HWND
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetWindowDC.argtypes = [wintypes.HWND]
u32.GetWindowDC.restype = wintypes.HDC
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
g32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

hwnd = int(u32.FindWindowW(None, "微信") or 0)
if not hwnd:
    sys.exit("没找到微信")

wr = wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(wr))
w, h = wr.right - wr.left, wr.bottom - wr.top
print("窗口 %dx%d" % (w, h))

hdc = u32.GetWindowDC(hwnd)
mdc = g32.CreateCompatibleDC(hdc)
bmp = g32.CreateCompatibleBitmap(hdc, w, h)
g32.SelectObject(mdc, bmp)
ok = u32.PrintWindow(hwnd, mdc, 2)
print("PrintWindow ->", ok)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


bi = BITMAPINFOHEADER()
bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bi.biWidth = w
bi.biHeight = -h            # 负数 = 自上而下
bi.biPlanes = 1
bi.biBitCount = 32
bi.biCompression = 0
buf = ctypes.create_string_buffer(w * h * 4)
g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
out = Path(r"<PROJECT_ROOT>\feizhi_pc\eval\_wechat_now.png")
img.save(out)
print("已存:", out)

g32.DeleteObject(bmp)
g32.DeleteDC(mdc)
u32.ReleaseDC(hwnd, hdc)
