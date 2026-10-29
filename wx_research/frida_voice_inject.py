# -*- coding: utf-8 -*-
"""把 TTS 音频喂进微信的 SILK 编码器，让微信以为是自己录的音。

原理（已实测确认）：
  微信 4.1.9.23 语音消息 = SILK v3，编码器 VoipEngine.dll!SKP_Silk_SDK_Encode
  每帧 320 samples / 16000 Hz / 单声道 s16le，调用点 Weixin.dll+0x60c8537。
  该函数第 3 个参数（args[2]）就是 PCM 输入缓冲，指向微信自己的堆内存。
  → 在 onEnter 里把这块缓冲覆写成我们的数据，其余流程（编码/上传/
    构造 voicemsg/发送）全部由微信自己完成。

触发：微信 4.1.9 的语音录制快捷键是**右 Alt**（按住说话，松开发送）。
本脚本用 ctypes 把微信窗口激活、点进输入框、按住右 Alt，
等 TTS 数据喂完立即松开 —— 于是发出这段语音。

用法：
    python frida_voice_inject.py --pcm <PROJECT_ROOT>\\tmp\\tts_16k.pcm [--arm-only]

--arm-only 只装 hook 不按键，用于手动验证。
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import frida

JS = r"""
'use strict';

function exp(name) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
    try { return Module.findExportByName(null, name); } catch (e) {}
    return null;
}

var pcmU8 = null;            // 我们的 PCM（Int16 小端）
var totalSamples = 0;
// 注意：不能叫 ptr —— frida 的全局 ptr() 是内置函数，会报 "ptr is read-only"
var cursor = 0;              // 已喂出的样本数
var enabled = false;
var stats = { calls: 0, filled: 0, silent: 0 };
var silence = null;

function ensureSilence(n) {
    if (!silence || silence.length < n * 2) silence = new Uint8Array(Math.max(n, 1024) * 2);
    return silence;
}

var voip = Process.findModuleByName('VoipEngine.dll');
if (!voip) {
    send({ t: 'err', msg: 'VoipEngine.dll 未加载' });
} else {
    var pEnc = voip.findExportByName('SKP_Silk_SDK_Encode');
    send({ t: 'info', msg: 'Encode=' + pEnc });

    Interceptor.attach(pEnc, {
        onEnter: function (a) {
            if (!enabled || !pcmU8) return;
            var n = a[3].toInt32();
            var buf = a[2];
            var avail = totalSamples - cursor;
            stats.calls++;
            if (avail <= 0) {
                // 数据已喂完：补静音，避免把残留缓冲当音频编出去
                buf.writeByteArray(ensureSilence(n).subarray(0, n * 2));
                stats.silent++;
                return;
            }
            var take = n < avail ? n : avail;
            buf.writeByteArray(pcmU8.subarray(cursor * 2, (cursor + take) * 2));
            if (take < n) {
                buf.add(take * 2).writeByteArray(ensureSilence(n - take).subarray(0, (n - take) * 2));
                stats.silent++;
            }
            cursor += take;
            stats.filled++;
        }
    });
    send({ t: 'hooked', msg: 'SKP_Silk_SDK_Encode 已挂钩，等待 arm()' });
}

// frida 的 QuickJS 没有 atob，用官方二进制通道：Python 侧 script.post(msg, bytes)
recv('pcm', function (msg, data) {
    var u8 = new Uint8Array(data);
    pcmU8 = u8;
    totalSamples = (u8.length / 2) | 0;
    cursor = 0;
    send({ t: 'pcm', bytes: u8.length, samples: totalSamples });
});

rpc.exports = {
    arm: function () {
        cursor = 0; stats = { calls: 0, filled: 0, silent: 0 };
        enabled = true;
        return true;
    },
    disarm: function () {
        enabled = false;
        return { cursor: cursor, total: totalSamples, calls: stats.calls,
                 filled: stats.filled, silent: stats.silent };
    },
    progress: function () {
        return { cursor: cursor, total: totalSamples, calls: stats.calls,
                 filled: stats.filled, silent: stats.silent, enabled: enabled };
    }
};
"""

# ---------- Win32 ----------
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

u32.GetForegroundWindow.restype = wintypes.HWND
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.FindWindowW.restype = wintypes.HWND
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.IsIconic.argtypes = [wintypes.HWND]
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, ctypes.c_void_p]
u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_void_p]
k32.GetCurrentThreadId.restype = wintypes.DWORD

VK_RMENU = 0xA5
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

INPUT_X, INPUT_Y = 740, 620      # 聊天输入框（2560x1440 实测坐标）


def find_wechat() -> int | None:
    h = u32.FindWindowW(None, "微信")
    if h:
        return h
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(hwnd, buf, 512)
        if buf.value.strip() == "微信":
            found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def focus_wechat(hwnd: int) -> bool:
    """把微信切到前台并校验。

    Windows 的前台锁定会让 SetForegroundWindow 静默失败（只剩任务栏闪烁）。
    分级重试：先 AttachThreadInput，仍失败则 SW_MINIMIZE + SW_RESTORE —— 后者
    会闪一下窗口，但几乎总能拿到前台。2026-10-15 实测：不做这层，按键会打到
    浏览器上，微信收不到右 Alt，Encode 调用数为 0。
    """
    hwnd = int(hwnd)
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)      # SW_RESTORE
        time.sleep(0.4)
    for attempt in range(3):
        pid = wintypes.DWORD()
        tid = u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        cur = k32.GetCurrentThreadId()
        u32.AttachThreadInput(cur, tid, True)
        u32.SetForegroundWindow(hwnd)
        u32.AttachThreadInput(cur, tid, False)
        time.sleep(0.45)
        if int(u32.GetForegroundWindow() or 0) == hwnd:
            return True
        u32.ShowWindow(hwnd, 6)      # SW_MINIMIZE
        time.sleep(0.28)
        u32.ShowWindow(hwnd, 9)      # SW_RESTORE
        time.sleep(0.45)
        if int(u32.GetForegroundWindow() or 0) == hwnd:
            return True
        print("  focus attempt %d failed, retrying" % (attempt + 1))
    return False


def click_input() -> None:
    u32.SetCursorPos(INPUT_X, INPUT_Y)
    time.sleep(0.15)
    u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.06)
    u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.35)


def ralt_down() -> None:
    u32.keybd_event(VK_RMENU, 0, KEYEVENTF_EXTENDEDKEY, None)


def ralt_up() -> None:
    u32.keybd_event(VK_RMENU, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, None)


def pick_wx_pid() -> int | None:
    try:
        procs = frida.get_local_device().enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    best = None
    for p in procs:
        if "weixin" in (p.name or "").lower():
            best = p.pid if best is None else best
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcm", default=r"<PROJECT_ROOT>\tmp\tts_16k.pcm")
    ap.add_argument("--arm-only", action="store_true")
    ap.add_argument("--max-hold", type=float, default=12.0)
    args = ap.parse_args()

    pcm_path = Path(args.pcm)
    if not pcm_path.exists():
        print("PCM 不存在: %s" % pcm_path)
        return 1
    raw = pcm_path.read_bytes()
    total_samples = len(raw) // 2
    print("PCM %s: %d samples = %.2f s @16k mono" % (
        pcm_path.name, total_samples, total_samples / 16000.0))

    pid = pick_wx_pid()
    if not pid:
        print("找不到 Weixin 进程")
        return 1
    print("attach pid=%d" % pid)
    session = frida.attach(pid)
    script = session.create_script(JS)
    script.on("message", lambda m, d: print("  [frida] %s" % m.get("payload", m)))
    script.load()

    ex = getattr(script, "exports_sync", None) or script.exports

    script.post({"type": "pcm"}, raw)
    t0 = time.time()
    n = 0
    while time.time() - t0 < 15:
        time.sleep(0.1)
        pr0 = ex.progress()
        if pr0["total"] > 0:
            n = pr0["total"]
            break
    if not n:
        print("PCM 未送进目标进程（recv 未触发）")
        session.detach()
        return 1
    print("loaded %d samples into target" % n)
    ex.arm()
    print("ARMED —— 现在按右 Alt 就会用自己的音频（--arm-only 模式下手动按）")

    if args.arm_only:
        print("arm-only：保持 300 秒，期间手动在微信里按住右 Alt 录音即可")
        time.sleep(300)
        print("disarm:", ex.disarm())
        session.detach()
        return 0

    hwnd = find_wechat()
    if not hwnd:
        print("找不到微信窗口")
        session.detach()
        return 1
    if not focus_wechat(hwnd):
        print("WARN: 无法把微信切到前台，按键可能无效（前台不是微信）")
    else:
        print("微信已在前台")
    click_input()

    print("R-Alt DOWN @ %.3f" % time.time())
    ralt_down()
    t0 = time.time()
    done = False
    while time.time() - t0 < args.max_hold:
        time.sleep(0.03)
        pr = ex.progress()
        if pr["cursor"] >= pr["total"] and pr["total"] > 0:
            done = True
            break
    ralt_up()
    print("R-Alt UP   @ %.3f  (%.2fs, fed %s/%s)" % (
        time.time(), time.time() - t0, pr["cursor"], pr["total"]))
    if not done:
        print("注意：未喂完（可能微信没进录音状态）")

    st = ex.disarm()
    print("disarm:", st)
    time.sleep(2.0)
    session.detach()
    print("完成。对端应收到一条语音。")
    return 0 if done else 2


if __name__ == "__main__":
    sys.exit(main())
