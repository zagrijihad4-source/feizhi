# -*- coding: utf-8 -*-
"""终极验证：语音是否真的能发到「当前会话以外」的人。

当前微信停在<OWNER>（或其他会话），我们把收件人改成 filehelper（文件传输助手），
发一条语音。判断依据：
  - 会话列表里「文件传输助手」那一行最后一条变成 [语音]
  - <OWNER>的会话不会多出这条

这一步过了，多用户化在语音这一环就没有障碍了：想发给谁就发给谁，
完全不需要切会话、不点任何东西。
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import tts     # noqa: E402
import voice   # noqa: E402

u32 = ctypes.windll.user32
PCM = ROOT / "tmp" / "_retarget_probe.pcm"
TARGET = "filehelper"          # 文件传输助手


def shot(name: str) -> Path:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    out = ROOT / "state" / name
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


def main() -> int:
    if not PCM.exists():
        print("缺 PCM：先跑 _voice_retarget_test.py")
        return 2

    print("发之前先截一张：", shot("_rt_before.png"))
    sender = voice.VoiceSender()
    if not sender._ensure():
        print("hook 不可用")
        return 2

    print("目标 = %s（当前窗口停在别的会话）" % TARGET)
    ok = sender.say_pcm(PCM, max_hold=20.0, peer=TARGET)
    print("say_pcm ->", ok)
    time.sleep(1.2)
    print("发完截一张：", shot("_rt_after.png"))
    sender.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
