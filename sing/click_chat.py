"""Open a WeChat conversation with a real mouse click.

PostMessage does not work on the conversation list (CEF-rendered), so this sends
actual cursor + button events, then restores the previous cursor position.
"""
import ctypes
import sys
import time
from ctypes import wintypes

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, ctypes.POINTER(wintypes.ULONG)]

LEFTDOWN, LEFTUP = 0x0002, 0x0004


def click(x, y):
    old = wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(old))
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    u32.mouse_event(LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.09)
    u32.mouse_event(LEFTUP, 0, 0, 0, None)
    time.sleep(0.9)
    u32.SetCursorPos(old.x, old.y)


def main():
    hwnd = int(sys.argv[1])
    rx = float(sys.argv[2]) if len(sys.argv) > 2 else 200
    ry = float(sys.argv[3]) if len(sys.argv) > 3 else 150
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    x = r.left + rx
    y = r.top + ry
    print("window", r.left, r.top, r.right, r.bottom, "-> click", x, y)
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    click(x, y)
    print("clicked")


if __name__ == "__main__":
    main()
