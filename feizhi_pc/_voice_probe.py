# -*- coding: utf-8 -*-
"""语音发送现场诊断：不动模型、不发消息，只把「按住说话」为什么按不动看清楚。

要看的东西：
  1. 微信窗口：hwnd / 是否最小化 / 是否可见 / 矩形 / 标题
  2. 微信进程：pid 是否与 hook 一致
  3. 输入框是否聚焦：GetGUIThreadInfo 的 hwndFocus
  4. 实测调用一次 SKP_Silk_SDK_Encode 触发，看 calls
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hwndActive", wt.HWND),
        ("hwndFocus", wt.HWND),
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize", wt.HWND),
        ("hwndCaret", wt.HWND),
        ("rcCaret", wt.RECT),
    ]


def win_info(hwnd: int) -> dict:
    if not hwnd:
        return {}
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, cls, 256)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    tid = u32.GetWindowThreadProcessId(hwnd, None)
    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    u32.GetGUIThreadInfo(tid, ctypes.byref(gti))
    fb = ctypes.create_unicode_buffer(256)
    if gti.hwndFocus:
        u32.GetWindowTextW(gti.hwndFocus, fb, 256)
    return {
        "hwnd": hwnd,
        "title": buf.value,
        "class": cls.value,
        "rect": [r.left, r.top, r.right, r.bottom],
        "size": [r.right - r.left, r.bottom - r.top],
        "iconic": bool(u32.IsIconic(hwnd)),
        "visible": bool(u32.IsWindowVisible(hwnd)),
        "tid": tid,
        "hwndFocus": gti.hwndFocus,
        "focusText": fb.value,
        "foregroundIsThis": int(u32.GetForegroundWindow() or 0) == hwnd,
    }


def main() -> int:
    import voice

    print("=" * 70)
    fg = int(u32.GetForegroundWindow() or 0)
    print("[前台]", json.dumps(win_info(fg), ensure_ascii=False))

    sender = voice.VoiceSender()
    print("[hook]", "ensure ->", sender._ensure())
    pid = voice._pick_pid()
    print("[微信]", json.dumps(win_info(sender._hwnd), ensure_ascii=False))
    print("[hook pid]", pid)

    # pid 与 hwnd 的归属进程是否一致
    hwnd_pid = wt.DWORD()
    u32.GetWindowThreadProcessId(sender._hwnd, ctypes.byref(hwnd_pid))
    print("[一致性] hwnd 归属 pid=%s，hook pid=%s，一致=%s"
          % (hwnd_pid.value, pid, hwnd_pid.value == pid))

    # 点开会话，确保「按住说话」按钮在
    sender.open_recent_chat()
    time.sleep(0.4)
    print("[点开会话后]", json.dumps(win_info(sender._hwnd), ensure_ascii=False))

    # 直接用现成 PCM 试发，观察 calls（默认不发，避免往会话里丢空语音）
    if "--send" not in sys.argv:
        print("[试发] 略过（加 --send 才真发一条 1 秒静音）")
        sender.close()
        return 0
    pcm = Path(__file__).parent / "state" / "_probe.pcm"
    if not pcm.exists():
        # 1 秒静音，只为触发按键与 hook，不需要真的有人声
        pcm.parent.mkdir(parents=True, exist_ok=True)
        pcm.write_bytes(b"\x00\x00" * 16000)
    print("[试发]", pcm, pcm.stat().st_size, "bytes")
    ok = sender._say_once(pcm, max_hold=12)
    print("[试发结果]", "成功" if ok else "失败")
    print("[试发后]", json.dumps(win_info(sender._hwnd), ensure_ascii=False))
    sender.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
