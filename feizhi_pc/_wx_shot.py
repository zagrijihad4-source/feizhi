# -*- coding: utf-8 -*-
"""截微信窗口那块屏幕，看它现在到底停在什么界面。

语音发不出去时最要紧的是看清窗口实际长什么样：会话开没开、输入框在哪、
有没有遮罩/弹窗/录音条残留。纯截图，不点任何东西。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32


def main() -> int:
    out = Path(__file__).parent / "state" / "_wxshot.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    import voice
    hwnd = voice.find_wechat_window()
    if not hwnd:
        print("找不到微信窗口")
        return 2
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = max(r.left, 0), max(r.top, 0)
    w, h = r.right - r.left, r.bottom - r.top
    print("微信窗口 hwnd=%s rect=(%d,%d)-(%d,%d) %dx%d" % (hwnd, r.left, r.top, r.right, r.bottom, w, h))
    dpi = u32.GetDpiForWindow(hwnd) or 96
    print("DPI=%d 缩放=%.2f" % (dpi, dpi / 96.0))

    # PowerShell 5.1 里 CopyFromScreen 的 Size 重载解析不稳（报 copyPixelOperation），
    # 改成截整屏再 Clone 裁剪 —— 全屏那句是 moments.py 验证过的写法。
    full = out.with_name("_wxshot_full.png")
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
    print("已保存:", out, out.stat().st_size if out.exists() else "缺失")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
