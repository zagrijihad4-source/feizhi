"""Send the SoulX cover to YG as a series of WeChat voice clips.

One frida attach for all clips (attaching per clip costs ~100 s).
LegionZone's topmost overlay can hold the Windows foreground lock, so the
foreground window is minimised via WM_SYSCOMMAND before each send.
"""
import ctypes
import glob
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

PEER = "<WXID_FRIEND_A>"  # YG
PCM_GLOB = r"<PROJECT_ROOT>\sing\outputs\soulx\pcm\slice*.pcm"

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = 0xF020


def fg_class():
    h = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, buf, 256)
    return int(h or 0), buf.value


def clear_foreground_overlay():
    """Minimise a stuck topmost overlay that blocks foreground activation."""
    h, cls = fg_class()
    if "LEGionZone" in cls or "Legion" in cls:
        u32.PostMessageW(h, WM_SYSCOMMAND, SC_MINIMIZE, 0)
        time.sleep(0.4)
        h2, cls2 = fg_class()
        print(f"  [fg] minimised {cls} -> now {cls2}")
        return True
    return False


def main():
    import bridge
    import voice

    clips = sorted(glob.glob(os.environ.get("SOLX_PCM_GLOB", PCM_GLOB)))
    if len(sys.argv) > 1:
        clips = clips[:int(sys.argv[1])]
    if len(sys.argv) > 2:
        clips = clips[int(sys.argv[2]):]
    if not clips:
        print("no pcm slices")
        return 1
    total = sum(os.path.getsize(p) // 2 / 16000.0 for p in clips)
    print(f"clips={len(clips)} total={total:.1f}s")

    b = bridge.HookBridge()
    print("worker_healthy:", b.worker_healthy())
    ob = bridge.OUTBOX
    nt = ob / "next.txt"
    if nt.exists():
        nt.write_text("", encoding="utf-8")   # 铁律：注入前清空槽位

    clear_foreground_overlay()
    print("wechat hwnd:", voice.find_wechat_window())

    sender = voice.VoiceSender()
    ok_count = 0
    for i, p in enumerate(clips):
        clear_foreground_overlay()
        dur = os.path.getsize(p) / 2 / 16000.0
        hold = dur + 26
        t0 = time.time()
        ok = sender.say_pcm(p, max_hold=hold, retries=1)
        print(f"[{i + 1}/{len(clips)}] {os.path.basename(p)} {dur:.1f}s -> {ok} "
              f"in {time.time() - t0:.1f}s", flush=True)
        if ok:
            ok_count += 1
        time.sleep(1.6)

    print(f"sent {ok_count}/{len(clips)}")
    return 0 if ok_count == len(clips) else 2


if __name__ == "__main__":
    sys.exit(main())
