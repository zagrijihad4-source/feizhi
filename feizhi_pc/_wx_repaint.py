# -*- coding: utf-8 -*-
"""微信窗口显示出来了但一片白：强制重绘，看能不能救活。

隐藏到托盘再恢复时，Qt/CEF 的内容不一定自己重绘。这里依次试：
  1. RedrawWindow 全量失效 + 立即更新
  2. SetWindowPos 轻微改尺寸再改回来（逼 Qt 重排）
每步之后截一张图，看白色区域有没有变回界面。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32

RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100
RDW_ERASENOW = 0x0200

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


def shot(hwnd: int, name: str) -> Path:
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    out = Path(__file__).parent / "state" / name
    ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
          "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
          "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height);"
          "$g=[System.Drawing.Graphics]::FromImage($bmp);"
          "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
          "$r=New-Object System.Drawing.Rectangle(%d,%d,%d,%d);"
          "$c=$bmp.Clone($r,$bmp.PixelFormat);"
          "$c.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png);"
          "$c.Dispose();$g.Dispose();$bmp.Dispose()"
          % (max(r.left, 0), max(r.top, 0), r.right - r.left, r.bottom - r.top, str(out)))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=90)
    return out


def whiteness(path: Path) -> float:
    """粗略白色占比：PNG 里亮像素比例（用 PowerShell 数，避免额外依赖）。"""
    ps = ("Add-Type -AssemblyName System.Drawing;"
          "$b=[System.Drawing.Bitmap]::FromFile('%s');"
          "$w=0;$t=0;"
          "for($y=0;$y -lt $b.Height;$y+=17){"
          "for($x=0;$x -lt $b.Width;$x+=17){"
          "$c=$b.GetPixel($x,$y);$t++;"
          "if($c.R -gt 235 -and $c.G -gt 235 -and $c.B -gt 235){$w++}}};"
          "$b.Dispose();"
          "[math]::Round(100.0*$w/$t,1)" % str(path))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=120)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return -1.0


def main() -> int:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    if not hwnd:
        print("找不到微信")
        return 2
    print("初始白色占比:", whiteness(shot(hwnd, "_r0.png")), "%")

    u32.RedrawWindow(hwnd, None, None,
                     RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN
                     | RDW_UPDATENOW | RDW_ERASENOW)
    time.sleep(1.0)
    print("RedrawWindow 后:", whiteness(shot(hwnd, "_r1.png")), "%")

    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    for dw, dh in ((1, 1), (0, 0)):
        u32.SetWindowPos(hwnd, 0, 0, 0, w + dw, h + dh,
                         SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(0.7)
    print("resize 抖动后:", whiteness(shot(hwnd, "_r2.png")), "%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
