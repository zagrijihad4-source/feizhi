# -*- coding: utf-8 -*-
"""用 PrintWindow 直接问窗口要它自己的画面 —— 不受任何遮挡影响。

屏幕截图会被盖在上面的窗口欺骗（刚才那张"全白"很可能就是白底的打印对话框）。
PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT) 拿的是窗口自己该画的东西，
白色占比低就说明微信本身渲染是好的，问题只在遮挡/前台。
"""
import ctypes
import ctypes.wintypes as wt
import sys

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32

BI_RGB = 0
DIB_RGB_COLORS = 0
PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def grab(hwnd: int) -> tuple[int, int, bytes]:
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return 0, 0, b""
    wdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(wdc)
    bmp = g32.CreateCompatibleBitmap(wdc, w, h)
    g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h          # 负数 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, wdc)
    return w, h, buf.raw


def main() -> int:
    wx = int(u32.FindWindowW(None, "微信") or 0)
    print("微信 hwnd =", wx, " 可见 =", bool(u32.IsWindowVisible(wx)))
    w, h, px = grab(wx)
    if not px:
        print("PrintWindow 拿不到内容")
        return 2
    total = white = 0
    step = 4 * 11                       # 每 11 个像素采一次
    for i in range(0, len(px) - 3, step):
        b, g, r = px[i], px[i + 1], px[i + 2]
        total += 1
        if r > 235 and g > 235 and b > 235:
            white += 1
    print("PrintWindow %dx%d，采样 %d 点，白色占比 %.1f%%"
          % (w, h, total, 100.0 * white / total))

    # 顺便看几个采样点的颜色，判断到底画了什么
    for tag, idx in (("左上", 0), ("中上", (w // 2) * 4),
                     ("中部", ((h // 2) * w + w // 2) * 4),
                     ("右下", ((h - 2) * w + w - 2) * 4)):
        if idx + 3 < len(px):
            print("  %s RGB=(%d,%d,%d)" % (tag, px[idx + 2], px[idx + 1], px[idx]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
