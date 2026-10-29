# -*- coding: utf-8 -*-
"""接着搜索验证：点联系人第一条 -> 确认会话打开 -> 真发一条语音看 calls。

这一段验证成功，整条修复方案就成立：
  搜索框定位（不再盲点列表第一行）+ 首次发送前就切好会话。
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


def click(x, y, hold=0.09):
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(hold)
    u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.3)


def main() -> int:
    import voice

    hwnd = voice.find_wechat_window()
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    s = (u32.GetDpiForWindow(hwnd) or 96) / 96.0
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

    # 搜索框
    click(r.left + int(150 * s), r.top + int(38 * s))
    for ch in "<OWNER>":
        u32.PostMessageW(hwnd, 0x0102, ctypes.c_void_p(ord(ch)), ctypes.c_void_p(1))
        time.sleep(0.12)
    time.sleep(1.2)

    # 联系人分组第一条：按截图量出来中心约 DIP (219, 119)
    click(r.left + int(219 * s), r.top + int(119 * s))
    time.sleep(1.2)
    print("已点联系人 ->", shot(hwnd, "_wx_s3_chat.png"))

    # 真发一条，看 calls
    sender = voice.VoiceSender()
    if not sender._ensure():
        print("hook 不可用")
        return 2
    pcm = Path(__file__).parent / "state" / "_probe.pcm"
    if not pcm.exists():
        pcm.write_bytes(b"\x00\x00" * 16000)
    ok = sender._say_once(pcm, max_hold=10)
    print("[发语音]", "成功" if ok else "失败")
    time.sleep(0.6)
    print("发完 ->", shot(hwnd, "_wx_s4_after.png"))
    sender.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
