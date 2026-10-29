# -*- coding: utf-8 -*-
"""绯栀发朋友圈（PC 端 UI 自动化链路）。

链路（已在 2026-10-15 深夜逐段实测）：
    1. 找到微信主窗（可见的、面积最大的 Qt 顶层窗口）
    2. 长按主窗右上角「摄像机」图标  -> 弹出标题为「朋友圈」的纯文字发表框
    3. 往发表框输入文字            -> 剪贴板 + 真实 Ctrl+V（Qt 不吃 WM_SETTEXT）
    4. 点「发表」按钮              -> 动态发布

为什么不用窗口类名/标题硬匹配：
    FindWindowW(None, "微信") 会命中一个 (-21333,-21333) 的幽灵窗；
    微信还有若干不可见的备用 Qt 窗口。判据必须是「可见 + 面积 + 标题」组合。

为什么坐标全部按比例算：
    实测过程中屏幕分辨率/缩放变过（2560x1440@150% -> 1536x864@125%），
    硬编码像素坐标必然失效。图标位置用「相对窗口右上角的 DIP 偏移」，
    按钮用「相对发表框的比例」。

输入法安全：写剪贴板会先备份后恢复，不污染用户剪贴板。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATES = HERE / "state"
STATES.mkdir(exist_ok=True)
CALIB_PATH = STATES / "moments_calib.json"
SHOT_DIR = HERE / "logs"

# ---- Win32 ----
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_CHAR = 0x0102
MK_LBUTTON = 0x0001
SW_RESTORE = 9

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL, VK_V, VK_A, VK_DELETE, VK_ESCAPE = 0x11, 0x56, 0x41, 0x2E, 0x1B
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetWindowRect.restype = wintypes.BOOL
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.IsWindowVisible.restype = wintypes.BOOL
u32.GetForegroundWindow.restype = wintypes.HWND
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.BringWindowToTop.argtypes = [wintypes.HWND]
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowThreadProcessId.restype = wintypes.DWORD
u32.GetDpiForWindow.argtypes = [wintypes.HWND]
u32.GetDpiForWindow.restype = wintypes.UINT
u32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
u32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
u32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
u32.OpenClipboard.argtypes = [wintypes.HWND]
u32.OpenClipboard.restype = wintypes.BOOL
u32.EmptyClipboard.restype = wintypes.BOOL
u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
u32.IsClipboardFormatAvailable.restype = wintypes.BOOL
u32.GetClipboardData.argtypes = [wintypes.UINT]
u32.GetClipboardData.restype = wintypes.HANDLE
u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
u32.SetClipboardData.restype = wintypes.HANDLE
u32.CloseClipboard.restype = wintypes.BOOL
k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wintypes.HGLOBAL
k32.GetCurrentThreadId.restype = wintypes.DWORD
u32.GetDC.argtypes = [wintypes.HWND]
u32.GetDC.restype = wintypes.HDC
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.DWORD
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


# ---- 标定默认值（2026-10-15 实测，144dpi 下量得，单位 DIP=1/96 inch）----
DEFAULT_CALIB = {
    # 摄像机图标中心：相对主窗右上角 (right - dx, top + dy)
    "camera_from_right_dip": 46.0,
    "camera_from_top_dip": 56.0,
    # 「发表」按钮中心：相对发表框的比例
    "publish_btn_ratio": [0.347, 0.837],
    "cancel_btn_ratio": [0.663, 0.837],
    # 点「取消」后微信会弹「将此次编辑保留？」模态浮层，这两个是它的按钮
    "keep_draft_btn_ratio": [0.341, 0.558],
    "discard_draft_btn_ratio": [0.661, 0.558],
    # 左侧栏那个圆形图标是「发现」（不是「朋友圈」）。
    # 只点它只会展开发现列表，内容区仍然空白、没有摄像机图标 ——
    # 必须再点列表第一项「朋友圈」才真正进入朋友圈页。实测踩过这个坑。
    "moments_tab_dip": [36.8, 252.0],
    # 发现列表第一项「朋友圈」：相对主窗左上角的 DIP 偏移
    "discover_moments_dip": [134.0, 106.7],
    # 长按时长
    "hold_ms": 1300,
    "note": "144dpi 实测：主窗 (1035,502,1349,972)，摄像机屏幕点 (2315,586) 命中纯文字发表框",
}


def load_calib() -> dict:
    if CALIB_PATH.exists():
        try:
            data = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_CALIB, **data}
        except Exception:
            pass
    return dict(DEFAULT_CALIB)


def save_calib(data: dict) -> None:
    CALIB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_dpi_aware() -> str:
    if u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        return "PerMonitorV2"
    try:
        if ctypes.WinDLL("shcore").SetProcessDpiAwareness(2) == 0:
            return "PerMonitor"
    except Exception:
        pass
    if u32.SetProcessDPIAware():
        return "System"
    return "none"


# 导入即设。只放在构造函数里是不够的：任何只 import 本模块、直接调 find_main_window /
# rect_of 的脚本都会忘记实例化 MomentsPublisher，于是静默拿到虚拟化坐标
# （窗口"看起来"缩小 1.25 倍，点击全部打偏）。实测踩过一次。
_DPI_MODE = set_dpi_aware()


def _title(h: int) -> str:
    b = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(h, b, 512)
    return b.value


def _class(h: int) -> str:
    b = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, b, 256)
    return b.value


def rect_of(h: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def enum_qt_windows() -> list[dict]:
    out: list[dict] = []

    def cb(hwnd, _lp):
        c = _class(hwnd)
        if not c.startswith("Qt5"):
            return True
        x, y, w, h = rect_of(hwnd)
        out.append({"hwnd": int(hwnd), "title": _title(hwnd), "cls": c,
                    "rect": (x, y, w, h), "area": max(0, w) * max(0, h),
                    "visible": bool(u32.IsWindowVisible(hwnd))})
        return True

    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]


def process_exe(hwnd: int) -> str:
    """窗口所属进程的可执行文件全路径（小写）。拿不到返回空串。"""
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.lower()
        return ""
    finally:
        k32.CloseHandle(h)


def find_main_window() -> dict | None:
    """微信主窗 = **微信进程的**、可见的、面积最大的 Qt 顶层窗口。

    ★ 必须校验进程身份（审查 R06）：旧判据只有「可见 + 面积 + Qt5」，
      桌上任何一个更大的 Qt 应用（编辑器、Qt 工具）都会被当成微信主窗，
      后续的真实鼠标点击就打到那个应用上去了。已离线复现。
    """
    cands = []
    for w in enum_qt_windows():
        if not w["visible"] or w["area"] <= 400000:
            continue
        exe = process_exe(w["hwnd"])
        if not ("weixin" in exe or "wechat" in exe):
            continue                      # 不是微信进程，排除
        w["exe"] = exe
        cands.append(w)
    return max(cands, key=lambda w: w["area"]) if cands else None


def find_publish_window() -> dict | None:
    """发表框 = **微信进程的**、标题「朋友圈」、可见、面积 15 万~60 万。

    同样要校验进程身份（审查 R06）：别的 Qt 应用也可能有个叫「朋友圈」的窗口。
    """
    wins = []
    for w in enum_qt_windows():
        if w["title"] != "朋友圈" or not w["visible"]:
            continue
        if not (150000 < w["area"] < 600000):
            continue
        exe = process_exe(w["hwnd"])
        if not ("weixin" in exe or "wechat" in exe):
            continue
        wins.append(w)
    return max(wins, key=lambda w: w["area"]) if wins else None


def activate(hwnd: int) -> bool:
    u32.ShowWindow(hwnd, SW_RESTORE)
    if int(u32.GetForegroundWindow() or 0) == hwnd:
        return True
    fg = int(u32.GetForegroundWindow() or 0)
    tid_cur = k32.GetCurrentThreadId()
    tid_fg = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    att = bool(u32.AttachThreadInput(tid_cur, tid_fg, True)) if tid_fg else False
    try:
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
    finally:
        if att:
            u32.AttachThreadInput(tid_cur, tid_fg, False)
    time.sleep(0.35)
    return int(u32.GetForegroundWindow() or 0) == hwnd


def _send_mouse(flags: int, sx: int = 0, sy: int = 0) -> None:
    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    inp = INPUT()
    inp.type = INPUT_MOUSE
    if flags & MOUSEEVENTF_ABSOLUTE:
        inp.u.mi.dx = int(sx * 65535 / max(1, sw - 1))
        inp.u.mi.dy = int(sy * 65535 / max(1, sh - 1))
    inp.u.mi.dwFlags = flags
    u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _send_key(vk: int, up: bool = False) -> None:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def humanize_on() -> bool:
    """拟人节奏开关（FEIZHI_HUMANIZE=0 可关，与项目其它模块一致）。

    动因：wechatauto-replica 作者本机实测触发过微信风控（被要求重新登录），
    结论是风控看的是「动作的时间分布」——固定间隔、瞬移光标、永远命中控件正中。
    所以这里只做三件事：落点微抖、光标分两段移入、等待时间随机化。
    """
    return os.environ.get("FEIZHI_HUMANIZE", "1").strip().lower() not in ("0", "false", "no")


def _sleep(lo: float, hi: float, humanize: bool) -> None:
    time.sleep(random.uniform(lo, hi) if humanize else lo)


def click_at(sx: int, sy: int, humanize: bool = False, hold_ms: int | None = None) -> None:
    if humanize:
        sx += random.randint(-3, 3)
        sy += random.randint(-2, 2)
        # 分两段移入，避免光标瞬移到控件正中
        _send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, sx - random.randint(30, 70),
                    sy - random.randint(8, 20))
        _sleep(0.06, 0.18, True)
    _send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, sx, sy)
    _sleep(0.1, 0.22, humanize)
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
    else:
        _sleep(0.05, 0.09, humanize)
    _send_mouse(MOUSEEVENTF_LEFTUP)


def long_press_at(sx: int, sy: int, hold_ms: int, humanize: bool = False) -> None:
    if humanize:
        sx += random.randint(-3, 3)
        sy += random.randint(-2, 2)
        _send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, sx - random.randint(30, 70),
                    sy - random.randint(8, 20))
        _sleep(0.06, 0.18, True)
    _send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, sx, sy)
    _sleep(0.12, 0.26, humanize)
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(hold_ms / 1000.0)
    _send_mouse(MOUSEEVENTF_LEFTUP)


def hotkey(mod: int, key: int) -> None:
    _send_key(mod)
    time.sleep(0.05)
    _send_key(key)
    time.sleep(0.05)
    _send_key(key, True)
    time.sleep(0.05)
    _send_key(mod, True)


def clipboard_get() -> str | None:
    if not u32.OpenClipboard(None):
        return None
    try:
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = k32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def clipboard_set(text: str) -> bool:
    if not u32.OpenClipboard(None):
        return False
    try:
        u32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = k32.GlobalLock(h)
        if not p:
            return False
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        u32.CloseClipboard()


def shot(path: Path) -> Path:
    path.parent.mkdir(exist_ok=True)
    ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
          "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
          "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height);"
          "$g=[System.Drawing.Graphics]::FromImage($bmp);"
          "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
          "$bmp.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png);"
          "$g.Dispose();$bmp.Dispose()" % str(path))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=90)
    return path


def camera_screen_point(main: dict, calib: dict | None = None) -> tuple[int, int]:
    """摄像机图标屏幕坐标 = 主窗右上角按 DIP 偏移换算。"""
    calib = calib or load_calib()
    x, y, w, h = main["rect"]
    dpi = u32.GetDpiForWindow(main["hwnd"]) or 96
    scale = dpi / 96.0
    sx = int(x + w - calib["camera_from_right_dip"] * scale)
    sy = int(y + calib["camera_from_top_dip"] * scale)
    return sx, sy


def moments_tab_point(main: dict, calib: dict | None = None) -> tuple[int, int]:
    """左侧栏「发现」图标屏幕坐标 = 主窗左上角按 DIP 偏移换算。"""
    calib = calib or load_calib()
    x, y, w, h = main["rect"]
    dpi = u32.GetDpiForWindow(main["hwnd"]) or 96
    scale = dpi / 96.0
    dx, dy = calib["moments_tab_dip"]
    return int(x + dx * scale), int(y + dy * scale)


def discover_first_point(main: dict, calib: dict | None = None) -> tuple[int, int]:
    """发现列表第一项「朋友圈」的屏幕坐标。"""
    calib = calib or load_calib()
    x, y, w, h = main["rect"]
    dpi = u32.GetDpiForWindow(main["hwnd"]) or 96
    scale = dpi / 96.0
    dx, dy = calib["discover_moments_dip"]
    return int(x + dx * scale), int(y + dy * scale)


def post_click_at(hwnd: int, sx: int, sy: int, hold_ms: int = 120) -> None:
    """PostMessage 版的鼠标点击：不移动真实光标、不激活窗口。

    实测对微信主窗（Qt 画的左侧栏、以及内容区的列表项）有效 ——
    用它可以在微信处于后台时完成切页，不会把用户的焦点抢走。
    """
    p = wintypes.POINT(sx, sy)
    u32.ScreenToClient(hwnd, ctypes.byref(p))
    lp = ((p.y & 0xFFFF) << 16) | (p.x & 0xFFFF)
    u32.PostMessageW(hwnd, WM_MOUSEMOVE, ctypes.c_void_p(0), ctypes.c_void_p(lp))
    time.sleep(0.08)
    u32.PostMessageW(hwnd, WM_LBUTTONDOWN, ctypes.c_void_p(MK_LBUTTON), ctypes.c_void_p(lp))
    time.sleep(hold_ms / 1000.0)
    u32.PostMessageW(hwnd, WM_LBUTTONUP, ctypes.c_void_p(0), ctypes.c_void_p(lp))


def publish_button_point(pub: dict, calib: dict | None = None, which: str = "publish") -> tuple[int, int]:
    """发表框内的按钮坐标。which: publish / cancel / keep_draft / discard_draft。"""
    calib = calib or load_calib()
    x, y, w, h = pub["rect"]
    rx, ry = calib["%s_btn_ratio" % which]
    return int(x + w * rx), int(y + h * ry)


def pixel_at(sx: int, sy: int) -> tuple[int, int, int]:
    """读屏幕某点的 (r,g,b)。"""
    hdc = u32.GetDC(None)
    try:
        c = gdi32.GetPixel(hdc, sx, sy)
    finally:
        u32.ReleaseDC(None, hdc)
    return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)


class Grab:
    """一块屏幕区域的像素快照（32 位 BGRA，top-down）。

    为什么不用 GetPixel 逐点扫：GDI 取屏幕像素每次调用约 2~3ms，
    扫 5 万点直接超时（实测 180 秒没跑完）。一次 BitBlt 抓下来之后
    就是纯内存字节访问，同样的扫描只要几毫秒。
    """

    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h
        src = u32.GetDC(None)
        try:
            mdc = gdi32.CreateCompatibleDC(src)
            bmp = gdi32.CreateCompatibleBitmap(src, w, h)
            old = gdi32.SelectObject(mdc, bmp)
            try:
                gdi32.BitBlt(mdc, 0, 0, w, h, src, x, y, SRCCOPY)
                bi = BITMAPINFO()
                bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bi.bmiHeader.biWidth = w
                bi.bmiHeader.biHeight = -h          # 负值 = top-down
                bi.bmiHeader.biPlanes = 1
                bi.bmiHeader.biBitCount = 32
                bi.bmiHeader.biCompression = 0
                buf = ctypes.create_string_buffer(w * h * 4)
                gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
                self.data = buf.raw
            finally:
                gdi32.SelectObject(mdc, old)
                gdi32.DeleteObject(bmp)
                gdi32.DeleteDC(mdc)
        finally:
            u32.ReleaseDC(None, src)

    def px(self, lx: int, ly: int) -> tuple[int, int, int]:
        """局部坐标 -> (r,g,b)。越界返回黑。"""
        if not (0 <= lx < self.w and 0 <= ly < self.h):
            return (0, 0, 0)
        i = (ly * self.w + lx) * 4
        d = self.data
        return (d[i + 2], d[i + 1], d[i])

    def green_ratio(self, lx: int, ly: int, rx: int, ry: int) -> float:
        """局部矩形内「微信绿」占比（2px 步进采样）。"""
        total = green = 0
        d = self.data
        for y in range(max(0, ly - ry), min(self.h, ly + ry + 1), 2):
            base = y * self.w * 4
            for x in range(max(0, lx - rx), min(self.w, lx + rx + 1), 2):
                i = base + x * 4
                b, g, r = d[i], d[i + 1], d[i + 2]
                total += 1
                if g > 110 and g > r + 40:
                    green += 1
        return green / total if total else 0.0


def green_ratio(cx: int, cy: int, rx: int, ry: int) -> float:
    """屏幕坐标下某矩形区域「微信绿」像素占比。"""
    g = Grab(cx - rx, cy - ry, rx * 2 + 1, ry * 2 + 1)
    return g.green_ratio(rx, ry, rx, ry)


def publish_button_enabled(pub: dict, calib: dict | None = None) -> bool:
    """「发表」按钮是否已激活（微信用它表示输入框里有没有内容）。

    实测：输入框为空时按钮是深灰，有内容时变成微信绿 #07C160。
    这是低成本确认「文字真的写进去了」的唯一信号 —— 不看它就会出现
    「Ctrl+V 被模态浮层吃掉、却报告写入成功」的假阳性。

    注意**必须扫一片区域**：按钮正中心是白色「发表」两个字，
    单点取色会读到白字像素，把绿色按钮判成灰的（踩过）。
    """
    x, y, w, h = pub["rect"]
    rx, ry = (calib or load_calib())["publish_btn_ratio"]
    cx, cy = int(x + w * rx), int(y + h * ry)
    return green_ratio(cx, cy, max(6, int(w * 0.10)), max(3, int(h * 0.02))) > 0.35


def camera_icon_ratio(main: dict, calib: dict | None = None, r: int = 30) -> float:
    """摄像机图标位置的白色像素占比 —— 用来判断"现在到底在不在朋友圈页"。

    摄像机只在朋友圈页存在，这是最便宜的页面身份判据（实测在页 0.10、
    不在页 0.00）。比"猜页面"可靠，也比截图便宜。
    """
    cx, cy = camera_screen_point(main, calib)
    g = Grab(cx - r, cy - r, r * 2, r * 2)
    d = g.data
    n = tot = 0
    for i in range(0, len(d), 8):
        b, gg, rr = d[i], d[i + 1], d[i + 2]
        tot += 1
        if rr > 170 and gg > 170 and b > 170:
            n += 1
    return n / tot if tot else 0.0


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


class MomentsPublisher:
    """朋友圈发布器。所有方法返回 (ok, detail) 便于上层判断。"""

    def __init__(self, calib: dict | None = None, verbose: bool = True,
                 humanize: bool | None = None, background: bool = True):
        self.calib = calib or load_calib()
        self.verbose = verbose
        self.humanize = humanize_on() if humanize is None else humanize
        # background=True：切页/长按/写入走 PostMessage 与 WM_CHAR，
        # 不移动真实光标、不抢前台（实测对微信主窗有效）。
        # 只有「发表」「取消」这类弹窗按钮仍需真实鼠标 —— 而发表框弹出时
        # 微信自己已把它带到前台，所以并不额外打扰用户。
        self.background = background
        self.dpi_mode = set_dpi_aware()

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    # --- 单步 ---
    def ensure_moments_page(self, main: dict) -> bool:
        """切到朋友圈页。返回是否自检到摄像机图标（= 确实在那一页）。

        要点：左侧栏那个圆形图标是「发现」，点它只会展开发现列表；
        必须再点列表第一项「朋友圈」才是真的进朋友圈 —— 只点第一步的话
        内容区是空白、根本没有摄像机，长按必然落空（这是今天最大的坑）。

        已经在朋友圈页时直接返回，不做多余点击。
        """
        if camera_icon_ratio(main, self.calib) > 0.02:
            self._log("已在朋友圈页")
            return True

        hwnd = main["hwnd"]
        for attempt in range(2):
            mx, my = moments_tab_point(main, self.calib)
            dx, dy = discover_first_point(main, self.calib)
            self._log("切朋友圈：点「发现」(%d,%d) -> 点列表首项 (%d,%d)" % (mx, my, dx, dy))
            if self.background:
                post_click_at(hwnd, mx, my, 200)
                time.sleep(1.0)
                post_click_at(hwnd, dx, dy, 200)
            else:
                click_at(mx, my, humanize=self.humanize, hold_ms=220)
                time.sleep(1.0)
                click_at(dx, dy, humanize=self.humanize, hold_ms=220)
            time.sleep(1.2)
            if camera_icon_ratio(main, self.calib) > 0.02:
                return True
            self._log("第 %d 次切页后仍未见到摄像机图标" % (attempt + 1))
        return False

    def open_text_editor(self, retries: int = 2) -> tuple[bool, dict]:
        """切到朋友圈页 -> 长按摄像机 -> 纯文字发表框。

        前置必须清场：残留的旧发表框会被 find_publish_window 认成"打开成功"，
        于是整轮都作用在那个旧窗口上（实测踩过这个假阳性）。
        """
        stale = find_publish_window()
        if stale:
            self._log("发现残留发表框 hwnd=%d，先清场" % stale["hwnd"])
            if not self.cancel():
                return False, {"stage": "precheck", "detail": "残留发表框无法清理，放弃本轮"}
        main = find_main_window()
        if not main:
            return False, {"stage": "find_main", "detail": "找不到微信主窗"}
        sx, sy = camera_screen_point(main, self.calib)
        self._log("主窗 hwnd=%d rect=%s -> 摄像机 (%d,%d)" % (main["hwnd"], main["rect"], sx, sy))
        if not self.background:
            if not activate(main["hwnd"]):
                # ★ 激活失败就中止（审查 R06）：旧代码只打一句 warning，
                #   然后照样发真实鼠标事件 —— 事件会落到"当前前台那个窗口"，
                #   可能是任何一个应用。
                return False, {"stage": "activate",
                               "detail": "微信主窗激活失败，已中止（避免误点其他窗口）"}

        page_ok = self.ensure_moments_page(main)
        if not page_ok:
            self._log("切页自检没通过，仍尝试长按（长按成功才是硬判据）")

        base = int(self.calib["hold_ms"])
        attempts = []
        for i in range(max(1, retries)):
            hold = int(base * (1.0 + 0.25 * i))
            if self.humanize:
                hold = int(hold * random.uniform(0.92, 1.08))
            if self.background:
                post_click_at(main["hwnd"], sx, sy, hold)      # down -> hold -> up
            else:
                long_press_at(sx, sy, hold, humanize=self.humanize)
            time.sleep(1.2 + random.uniform(0, 0.5) if self.humanize else 1.2)
            pub = find_publish_window()
            attempts.append({"try": i + 1, "hold_ms": hold, "found": bool(pub)})
            if pub:
                self._log("发表框 hwnd=%d rect=%s（第 %d 次尝试）" % (pub["hwnd"], pub["rect"], i + 1))
                return True, pub
            if i + 1 < retries:
                self.ensure_moments_page(main)

        return False, {"stage": "open_text_editor", "detail": "长按后未出现发表框",
                       "camera_point": (sx, sy), "main": main, "attempts": attempts,
                       "page_ok": page_ok}

    def write_text(self, text: str) -> tuple[bool, dict]:
        """把文字写进发表框。

        后台模式优先走 WM_CHAR 逐字符：实测可用，且不需要焦点、不碰用户剪贴板。
        没生效再回退「剪贴板 + 真实 Ctrl+V」（那条需要窗口前台）。
        """
        pub = find_publish_window()
        if not pub:
            return False, {"stage": "write_text", "detail": "发表框不存在"}

        if self.background:
            hwnd = pub["hwnd"]
            for ch in text:
                code = ord(ch)
                if code > 0xFFFF:                       # 代理对（emoji 等）
                    code -= 0x10000
                    for c in (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)):
                        u32.PostMessageW(hwnd, WM_CHAR, ctypes.c_void_p(c),
                                         ctypes.c_void_p(0))
                        time.sleep(0.01)
                else:
                    u32.PostMessageW(hwnd, WM_CHAR, ctypes.c_void_p(code),
                                     ctypes.c_void_p(0))
                    time.sleep(0.02)
            time.sleep(0.9)
            if publish_button_enabled(pub, self.calib):
                self._log("WM_CHAR 写入 %d 字（后台，未动剪贴板）" % len(text))
                return True, {"stage": "write_text", "chars": len(text),
                              "button_enabled": True, "mode": "wm_char"}
            self._log("WM_CHAR 未生效，回退剪贴板路线")

        activate(pub["hwnd"])
        old = clipboard_get()
        ok_clip = clipboard_set(text)
        if not ok_clip:
            return False, {"stage": "write_text", "detail": "写剪贴板失败"}
        time.sleep(0.25)
        hotkey(VK_CONTROL, VK_V)
        time.sleep(0.8)
        if old is not None:
            time.sleep(0.15)
            clipboard_set(old)
        enabled = publish_button_enabled(pub, self.calib)
        self._log("已写入 %d 字（剪贴板已还原），发表按钮激活=%s" % (len(text), enabled))
        return enabled, {"stage": "write_text", "chars": len(text), "button_enabled": enabled,
                         "mode": "clipboard",
                         "detail": "" if enabled else "写入后「发表」按钮仍是灰的：文字没进去"}

    def click_publish(self) -> tuple[bool, dict]:
        """点「发表」按钮。调用前务必确认输入框已有内容。"""
        pub = find_publish_window()
        if not pub:
            return False, {"stage": "click_publish", "detail": "发表框不存在"}
        if not activate(pub["hwnd"]):
            # 激活失败不能硬点（审查 R06）：真实鼠标会打到当前前台那个窗口
            return False, {"stage": "click_publish",
                           "detail": "发表框激活失败，已中止（避免误点其他窗口）"}
        px, py = publish_button_point(pub, self.calib, "publish")
        self._log("点击发表 (%d,%d)" % (px, py))
        click_at(px, py, humanize=self.humanize)
        time.sleep(2.0)
        gone = find_publish_window() is None
        self._log("发表框已关闭=%s" % gone)
        return gone, {"stage": "click_publish", "point": (px, py), "closed": gone}

    def _dismiss_keep_draft(self, discard: bool = True) -> bool:
        """处理点「取消」后弹出的「将此次编辑保留？」模态浮层。

        这层浮层盖在输入框上，会把后续所有 Ctrl+V 吃掉（实测踩过），
        所以关窗必须把它处理掉，不能只点一次「取消」。
        """
        pub = find_publish_window()
        if not pub:
            return False
        which = "discard_draft" if discard else "keep_draft"
        px, py = publish_button_point(pub, self.calib, which)
        self._log("确认浮层：点「%s」(%d,%d)" % ("不保留" if discard else "保留", px, py))
        click_at(px, py, humanize=self.humanize)
        time.sleep(0.8)
        return find_publish_window() is None

    def cancel(self) -> bool:
        """关掉发表框（清场）。返回是否确认关闭。

        流程：点「取消」-> 若仍存在说明弹了「保留编辑？」浮层 -> 点「不保留」。
        不用 ESC 兜底：ESC 走同一个浮层，只会把自己绕回去。
        """
        pub = find_publish_window()
        if not pub:
            return True
        if not activate(pub["hwnd"]):
            self._log("发表框激活失败，取消操作中止（避免误点其他窗口）")
            return False
        cx, cy = publish_button_point(pub, self.calib, "cancel")
        self._log("点击取消 (%d,%d)" % (cx, cy))
        click_at(cx, cy, humanize=self.humanize)
        time.sleep(0.9)
        if find_publish_window() is None:
            return True
        if self._dismiss_keep_draft(discard=True):
            self._log("发表框已清理")
            return True
        # 浮层比例可能随版本变化：两个按钮都试一遍，仍未关就认输（不硬来）
        for which in ("keep_draft", "discard_draft"):
            pub = find_publish_window()
            if not pub:
                return True
            px, py = publish_button_point(pub, self.calib, which)
            self._log("兜底再点一次「%s」(%d,%d)" % (which, px, py))
            click_at(px, py, humanize=self.humanize)
            time.sleep(0.8)
            if find_publish_window() is None:
                return True
        self._log("警告: 发表框仍未关闭")
        return False

    # --- 全流程 ---
    def _restore_foreground(self, prev_fg: int) -> bool:
        """把前台还给流程开始前那个窗口（微信弹发表框时会自己抢走它）。

        只在"当前前台属于微信进程"时才归还 —— 如果用户在流程期间自己切到了
        别的窗口，不能把它抢回来。
        """
        if not prev_fg:
            return False
        cur = int(u32.GetForegroundWindow() or 0)
        if cur == prev_fg or not cur:
            return True
        cur_pid, prev_pid = window_pid(cur), window_pid(prev_fg)
        main = find_main_window()
        wechat_pid = window_pid(main["hwnd"]) if main else 0
        if wechat_pid and cur_pid == wechat_pid and prev_pid != wechat_pid:
            return activate(prev_fg)
        return False

    def post(self, text: str, dry_run: bool = False) -> dict:
        """长按 -> 写文字 ->（可选）点发表。dry_run 时停在发表前并截图。

        失败时自动取消，不留半开的发表框（避免草稿残留在微信里）。
        流程结束会把前台还给原来的窗口。
        """
        prev_fg = int(u32.GetForegroundWindow() or 0)
        result: dict = {"text": text, "dry_run": dry_run, "dpi_mode": self.dpi_mode,
                        "humanize": self.humanize, "background": self.background}
        ok, info = self.open_text_editor()
        result["open"] = info
        if not ok:
            result["ok"] = False
            return result
        ok, info = self.write_text(text)
        result["write"] = info
        if not ok:
            self.cancel()
            result["ok"] = False
            result["note"] = "写入失败，已清场"
            result["foreground_restored"] = self._restore_foreground(prev_fg)
            return result
        stamp = time.strftime("%Y%m%d_%H%M%S")
        result["shot_before_publish"] = str(shot(SHOT_DIR / ("moments_%s_before.png" % stamp)))
        if dry_run:
            result["ok"] = True
            result["note"] = "dry_run：已停在发表前，输入框内容待人工确认"
            result["foreground_restored"] = self._restore_foreground(prev_fg)
            return result
        ok, info = self.click_publish()
        result["publish"] = info
        result["ok"] = ok
        result["shot_after_publish"] = str(shot(SHOT_DIR / ("moments_%s_after.png" % stamp)))
        result["foreground_restored"] = self._restore_foreground(prev_fg)
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description="绯栀发朋友圈")
    ap.add_argument("action", choices=["open", "write", "publish", "cancel", "post", "point", "shot"])
    ap.add_argument("--text", default="")
    ap.add_argument("--dry-run", action="store_true", help="只到发表前，不点发表")
    args = ap.parse_args()

    pub_inst = MomentsPublisher()
    if args.action == "point":
        main_win = find_main_window()
        if not main_win:
            print("找不到微信主窗")
            return 1
        sx, sy = camera_screen_point(main_win, pub_inst.calib)
        print(json.dumps({"dpi_mode": pub_inst.dpi_mode, "main": main_win,
                          "camera_point": (sx, sy),
                          "publish": find_publish_window()}, ensure_ascii=False, indent=2))
        return 0
    if args.action == "open":
        ok, info = pub_inst.open_text_editor()
        print(json.dumps({"ok": ok, "info": info}, ensure_ascii=False, default=str))
        return 0 if ok else 1
    if args.action == "write":
        ok, info = pub_inst.write_text(args.text)
        print(json.dumps({"ok": ok, "info": info}, ensure_ascii=False, default=str))
        return 0 if ok else 1
    if args.action == "publish":
        ok, info = pub_inst.click_publish()
        print(json.dumps({"ok": ok, "info": info}, ensure_ascii=False, default=str))
        return 0 if ok else 1
    if args.action == "cancel":
        ok = pub_inst.cancel()
        print(json.dumps({"ok": ok, "window_closed": find_publish_window() is None},
                         ensure_ascii=False))
        return 0 if ok else 1
    if args.action == "shot":
        print(shot(SHOT_DIR / ("moments_shot_%s.png" % time.strftime("%Y%m%d_%H%M%S"))))
        return 0
    res = pub_inst.post(args.text, dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, default=str, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
