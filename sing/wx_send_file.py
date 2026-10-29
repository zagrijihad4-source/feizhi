"""Put files on the Windows clipboard (CF_HDROP) and paste them into WeChat.

The hook bridge only speaks text/sticker/image, so real files need the real UI.
Clipboard paste is the least fragile way: no coordinate hunting, no file dialog.

usage: python wx_send_file.py <file1> [file2 ...] [--send]
  without --send it only pastes (so the result can be inspected on screen)
"""
import ctypes
import struct
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

CF_HDROP = 15
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


def set_clipboard_files(paths):
    files = "".join(p + "\0" for p in paths) + "\0"
    data = files.encode("utf-16-le")
    header = 20                      # sizeof(DROPFILES)
    size = header + len(data)
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
    if not h:
        raise OSError("GlobalAlloc failed")
    p = kernel32.GlobalLock(h)
    if not p:
        kernel32.GlobalFree(h)
        raise OSError("GlobalLock failed")
    hdr = ctypes.create_string_buffer(header)
    struct.pack_into("<I", hdr, 0, header)   # pFiles: offset of the file list
    struct.pack_into("<ii", hdr, 4, 0, 0)    # pt: drop point
    struct.pack_into("<ii", hdr, 12, 0, 1)   # fNC = 0, fWide = 1 (UTF-16)
    ctypes.memmove(p, hdr, header)
    ctypes.memmove(p + header, data, len(data))
    kernel32.GlobalUnlock(h)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(h)
        raise OSError("OpenClipboard failed (is another app holding it?)")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_HDROP, h):
            raise OSError("SetClipboardData failed")
        # ownership transfers to the system; must not free h here
    finally:
        user32.CloseClipboard()


def press_ctrl_v():
    user32.keybd_event(VK_CONTROL, 0, 0, None)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, 0, None)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, None)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, None)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_send = "--send" in sys.argv
    if not args:
        raise SystemExit("usage: wx_send_file.py <file> [...] [--send]")

    import os
    paths = [os.path.abspath(a) for a in args]
    for p in paths:
        if not os.path.exists(p):
            raise SystemExit("missing: %s" % p)
        print("  file: %-50s %.2f MB" % (os.path.basename(p), os.path.getsize(p) / 1048576))

    import voice

    hwnd = voice.find_wechat_window()
    print("wechat hwnd:", hwnd)
    if not voice.force_foreground(hwnd):
        print("WARN: could not raise WeChat to foreground")
    time.sleep(0.45)

    print("clipboard: copying %d file(s)" % len(paths))
    set_clipboard_files(paths)
    time.sleep(0.35)

    print("pasting (Ctrl+V) ...")
    press_ctrl_v()
    time.sleep(1.6)

    if do_send:
        print("pressing Enter to send")
        user32.keybd_event(0x0D, 0, 0, None)
        time.sleep(0.05)
        user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, None)
        time.sleep(1.2)
        print("sent")
    else:
        print("pasted only (no --send); check the screen")


if __name__ == "__main__":
    main()
