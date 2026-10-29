"""Send the three comparison audio files to the Api conversation as files.

The hook bridge cannot send files, and WeChat's Qt client only accepts a
real-focus Ctrl+V, so: activate the window, click the conversation, clear the
composer, then for each file put it on the clipboard through cua-driver (which
writes a proper CF_HDROP) and paste with keybd_event.

usage: python send_files_cua.py [--send]
"""
import ctypes
import json
import subprocess
import sys
import time

import voice  # noqa: F401  (adds feizhi_pc to path via its own sys.path entry below)

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import voice  # noqa: E402

from PIL import ImageGrab  # noqa: E402

FILES = [
    r"<PROJECT_ROOT>\sing\outputs\compare\01-原唱-潮汐.wav",
    r"<PROJECT_ROOT>\sing\outputs\compare\02-模型说话.wav",
    r"<PROJECT_ROOT>\sing\outputs\compare\03-模型唱歌-潮汐.wav",
]
HERE = None
CUA = "cua-driver"
VK_CONTROL, VK_V, VK_A, VK_RETURN = 0x11, 0x56, 0x41, 0x0D
KEYUP = 0x0002


def chk(desc, ret):
    print("  %-28s %s" % (desc, ret))
    return ret


def cua(tool, payload):
    p = subprocess.run([CUA, "call", tool], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=60, creationflags=0x08000000)
    return (p.stdout or "").strip() or (p.stderr or "").strip()


def key(vk, up=False):
    ctypes.windll.user32.keybd_event(vk, 0, KEYUP if up else 0, None)


def combo(mod_vk, vk):
    key(mod_vk)
    time.sleep(0.06)
    key(vk)
    time.sleep(0.06)
    key(vk, True)
    time.sleep(0.06)
    key(mod_vk, True)


def shot(path):
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    r = wt.RECT()
    u.GetWindowRect(ctypes.c_void_p(2885544), ctypes.byref(r))
    ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom)).save(path)


def main():
    do_send = "--send" in sys.argv
    hwnd = voice.find_wechat_window()
    print("wechat:", hwnd)
    voice.force_foreground(hwnd)
    time.sleep(0.6)

    u = ctypes.windll.user32
    # click the Api row in the conversation list (window-local 250,215)
    u.SetCursorPos(87 + 250, 81 + 215)
    time.sleep(0.25)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(2.2)
    print("clicked Api conversation")

    # clear whatever is in the composer
    combo(VK_CONTROL, VK_A)
    time.sleep(0.15)
    key(0x2E)  # Delete
    key(0x2E, True)
    time.sleep(0.4)
    print("composer cleared")

    for i, f in enumerate(FILES, 1):
        r = cua("clipboard_write", {"file_path": f})
        ok = "CF_HDROP" in r
        print("  [%d/%d] %-22s clipboard=%s" % (i, len(FILES), f.split("\\")[-1], ok))
        time.sleep(0.35)
        combo(VK_CONTROL, VK_V)
        time.sleep(1.4)

    shot(r"<PROJECT_ROOT>\tmp\files_pasted.png")
    print("pasted all, screenshot saved")

    if do_send:
        key(VK_RETURN)
        time.sleep(0.06)
        key(VK_RETURN, True)
        time.sleep(2.0)
        shot(r"<PROJECT_ROOT>\tmp\files_sent.png")
        print("Enter pressed")


if __name__ == "__main__":
    main()
