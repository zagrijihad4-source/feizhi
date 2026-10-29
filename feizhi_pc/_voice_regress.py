# -*- coding: utf-8 -*-
"""关键验证：把微信停留在「腾讯新闻」公众号会话（复现原始故障），
再让 voice.say(peer=<OWNER>) 走一遍，看它能不能自己切回<OWNER>把语音发出去。

这就是 2026-10-28 12:06 之后 calls=0 的现场复刻：
公众号推送把会话列表顶到最上，/之前盲点第一行就点了公众号只读页面，
那里没有输入框也没有按住说话按钮。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32
LEFTDOWN, LEFTUP = 0x0002, 0x0004
PEER = "<WXID_FRIEND_A>"


def shot(name: str) -> Path:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
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


def click_at(x: int, y: int, hold: float = 0.09) -> None:
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u32.mouse_event(LEFTDOWN, 0, 0, 0, None)
    time.sleep(hold)
    u32.mouse_event(LEFTUP, 0, 0, 0, None)
    time.sleep(0.3)


def main() -> int:
    import voice

    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    s = (u32.GetDpiForWindow(hwnd) or 96) / 96.0
    u32.ShowWindow(hwnd, 9)
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.6)

    # 腾讯新闻在会话列表第 3 行：按截图 DIP 约 (200, 168)
    print("点开腾讯新闻会话（复现故障现场）…")
    click_at(r.left + int(200 * s), r.top + int(168 * s))
    time.sleep(1.0)
    print("  已切到公众号 ->", shot("_t1_gzh.png"))

    print("现在让 voice.say 自己切回<OWNER>并发语音…")
    t0 = time.time()
    ok = voice.say("测试一下，我看看能不能自己找回你的窗口", "温柔", PEER)
    print("  结果: %s  耗时 %.1fs" % ("成功" if ok else "失败", time.time() - t0))
    time.sleep(0.6)
    print("  发完 ->", shot("_t2_after.png"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
