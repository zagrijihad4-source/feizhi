"""Send WeChat voice clips, resolving the Weixin PID from its main window.

voice._pick_pid() relies on frida enumerating processes, which does not list
weixin on this machine even though attaching by PID works fine. So find the
toplevel window titled 微信, read its owning PID, and hand that to VoiceSender.
"""
import ctypes
import glob
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.ULONG)]
u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WM_SYSCOMMAND, SC_MINIMIZE = 0x0112, 0xF020


def weixin_pid():
    found = []

    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == "微信":
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((hwnd, pid.value, buf.value))
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return found


def clear_overlay():
    """A stuck topmost window holds the foreground lock and blocks the hook."""
    h = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, cls, 256)
    u32.GetWindowTextW(h, buf, 256)
    if "LEGionZone" in cls.value or "Legion" in cls.value:
        u32.PostMessageW(h, WM_SYSCOMMAND, SC_MINIMIZE, 0)
        time.sleep(0.4)
        return True
    return False


def activate(hwnd):
    """Bring WeChat to the foreground; keybd_event only reaches the fg window."""
    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    u32.BringWindowToTop(hwnd)
    ok = bool(u32.SetForegroundWindow(hwnd))
    if not ok:
        # attach to the current foreground thread, then retry
        fg = u32.GetForegroundWindow()
        tf = u32.GetWindowThreadProcessId(fg, None)
        me = ctypes.windll.kernel32.GetCurrentThreadId()
        u32.AttachThreadInput(me, tf, True)
        u32.ShowWindow(hwnd, 9)
        u32.BringWindowToTop(hwnd)
        ok = bool(u32.SetForegroundWindow(hwnd))
        u32.AttachThreadInput(me, tf, False)
    time.sleep(0.5)
    now = u32.GetForegroundWindow()
    return ok or now == hwnd, now


def open_chat(hwnd):
    """Click the first conversation so the hold-to-talk button exists again.

    The conversation list is CEF-rendered: PostMessage is ignored, so this sends
    real cursor/button events. Client-area y for the first row is ~95 (the
    PrintWindow screenshot sits ~60 px lower because of the title bar).
    """
    old = wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(old))
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = r.left + 200, r.top + 95
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    u32.mouse_event(0x0002, 0, 0, 0, None)
    time.sleep(0.09)
    u32.mouse_event(0x0004, 0, 0, 0, None)
    time.sleep(1.1)
    u32.SetCursorPos(old.x, old.y)


def main():
    pattern = os.environ.get("SOLX_PCM_GLOB", "")
    clips = sorted(glob.glob(pattern)) if pattern else []
    if not clips:
        print("no pcm (set SOLX_PCM_GLOB)")
        return 1
    wins = weixin_pid()
    print("weixin windows:", wins)
    if not wins:
        print("Weixin is not running")
        return 2
    hwnd, pid, _ = wins[0]

    import bridge
    import voice

    print("bridge worker:", bridge.HookBridge().worker_healthy())
    voice._pick_pid = lambda: pid
    voice.find_wechat_window = lambda: hwnd      # WeChat restarted -> old hwnd is dead
    print("forced pid:", pid, "hwnd:", hwnd)

    sender = voice.VoiceSender()
    sender._hwnd = hwnd                           # _connect() may have cached the stale one
    if os.environ.get("SKIP_OPEN_CHAT") == "1":
        print("  skip auto-open: a chat is already open")
    else:
        open_chat(hwnd)
    ok_n = 0
    for i, p in enumerate(clips):
        clear_overlay()
        act, now = activate(hwnd)
        print('  foreground ->', now, 'activated:', act)
        dur = os.path.getsize(p) / 2 / 16000.0
        t0 = time.time()
        ok = sender.say_pcm(p, max_hold=dur + 26, retries=1)
        print("[%d/%d] %s %.1fs -> %s in %.1fs"
              % (i + 1, len(clips), os.path.basename(p), dur, ok, time.time() - t0), flush=True)
        if ok:
            ok_n += 1
        time.sleep(1.6)
    print("sent %d/%d" % (ok_n, len(clips)))
    return 0 if ok_n == len(clips) else 3


if __name__ == "__main__":
    sys.exit(main())
