# -*- coding: utf-8 -*-
"""用最接近用户操作的方式恢复微信界面：最小化 -> 还原。

比起直接 ShowWindow(SW_SHOW)，SW_MINIMIZE 再 SW_RESTORE 走的是正常的
窗口状态机，Qt 会收到完整的 show/hide/resize 事件序列，通常会重新布局。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32


def whiteness(hwnd: int, name: str) -> float:
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
          "$c.Dispose();$g.Dispose();$bmp.Dispose();"
          "$b2=[System.Drawing.Bitmap]::FromFile('%s');"
          "$w=0;$t=0;"
          "for($y=0;$y -lt $b2.Height;$y+=17){"
          "for($x=0;$x -lt $b2.Width;$x+=17){"
          "$p=$b2.GetPixel($x,$y);$t++;"
          "if($p.R -gt 235 -and $p.G -gt 235 -and $p.B -gt 235){$w++}}};"
          "$b2.Dispose();"
          "[math]::Round(100.0*$w/$t,1)"
          % (max(r.left, 0), max(r.top, 0), r.right - r.left, r.bottom - r.top,
             str(out), str(out)))
    r2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                        capture_output=True, text=True, timeout=120)
    try:
        return float(r2.stdout.strip())
    except ValueError:
        return -1.0


def main() -> int:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    print("白色占比(初始):", whiteness(hwnd, "_m0.png"), "%")

    print("最小化…")
    u32.ShowWindow(hwnd, 6)          # SW_MINIMIZE
    time.sleep(1.0)

    print("还原…")
    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    time.sleep(1.5)
    u32.SetForegroundWindow(hwnd)
    time.sleep(1.2)
    print("白色占比(还原后):", whiteness(hwnd, "_m1.png"), "%")

    for i in range(3):
        time.sleep(1.0)
        print("  等待重绘 %d: %s %%" % (i + 1, whiteness(hwnd, "_m2_%d.png" % i)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
