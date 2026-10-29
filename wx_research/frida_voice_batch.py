# -*- coding: utf-8 -*-
"""批量发语音：把 MiMo 的每个预置音色各发一条微信语音，供对比挑选。

每条自报音色名（「我是冰糖，喂，能听到吗？」），所以听的时候不用对着顺序猜。

用法：
    python frida_voice_batch.py [--only 冰糖,茉莉] [--gap 1.5]
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import frida

PC = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(PC))

JS = r"""
'use strict';

function exp(name) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
    try { return Module.findExportByName(null, name); } catch (e) {}
    return null;
}

var pcmU8 = null;
var totalSamples = 0;
var cursor = 0;
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
    Interceptor.attach(pEnc, {
        onEnter: function (a) {
            if (!enabled || !pcmU8) return;
            var n = a[3].toInt32();
            var buf = a[2];
            var avail = totalSamples - cursor;
            stats.calls++;
            if (avail <= 0) {
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
    send({ t: 'hooked', msg: 'Encode hooked' });
}

// 不用 recv/post 传大数据：frida 的 recv 处理器在一次触发后就失效，
// 批量发时第二遍就收不到（2026-10-15 实测 9 条只成功 2 条）。
// 改用 rpc + frida 的 File API 直接读 PCM 文件，可重复调用且无大小限制。
rpc.exports = {
    loadfile: function (path) {
        var buf = null;
        // frida 的 File API 在不同版本里形态不一：静态 readAllBytes / 实例方法 / readBytes+size
        try {
            if (typeof File.readAllBytes === 'function') {
                buf = File.readAllBytes(path);
            }
        } catch (e) {}
        if (!buf) {
            var f = new File(path, 'rb');
            try {
                if (typeof f.readAllBytes === 'function') {
                    buf = f.readAllBytes();
                } else if (typeof f.readBytes === 'function') {
                    buf = f.readBytes(f.size);
                }
            } finally {
                try { f.close(); } catch (e) {}
            }
        }
        if (!buf) throw new Error('无法读取 PCM 文件: ' + path);
        pcmU8 = new Uint8Array(buf);
        totalSamples = (pcmU8.length / 2) | 0;
        cursor = 0;
        return totalSamples;
    },
    arm: function () { cursor = 0; stats = { calls: 0, filled: 0, silent: 0 }; enabled = true; return true; },
    disarm: function () { enabled = false; return { cursor: cursor, total: totalSamples, calls: stats.calls, filled: stats.filled, silent: stats.silent }; },
    progress: function () { return { cursor: cursor, total: totalSamples, calls: stats.calls, filled: stats.filled, silent: stats.silent }; }
};
"""

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
u32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_void_p]
k32.GetCurrentThreadId.restype = wintypes.DWORD

VK_RMENU = 0xA5
EXT = 0x0001
UP = 0x0002
INPUT_X, INPUT_Y = 740, 620

# ---- 免前台的按键投递（2026-10-15 实测成立）----
# 微信的「按住右 Alt 说话」原本要求窗口有焦点，会抢用户前台。改成：
#   1) keybd_event 让**系统键盘状态**里 Alt 真的按下 —— 微信随后会校验这个，
#      只发消息不按真键的话，录音只能撑 0.24 秒就结束（实测 12 帧）。
#   2) PostMessage(WM_KEYDOWN) 把按键消息单独投递给微信窗口 —— 不需要它有焦点。
# 实测：2.5 秒录音共 112 帧，前台全程是浏览器，未被抢。
# 注意：必须 WM_KEYDOWN，WM_SYSKEYDOWN 那条路不生效。
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
SCAN_RALT = 0x38
LP_EXT, LP_CTX, LP_PREV, LP_TRANS = 1 << 24, 1 << 29, 1 << 30, 1 << 31
u32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]


def ralt_lp(down: bool) -> int:
    """右 Alt 的按键消息 lParam：扫描码 + 扩展键 + Alt 上下文位。"""
    v = 1 | (SCAN_RALT << 16) | LP_EXT | LP_CTX
    if not down:
        v |= LP_PREV | LP_TRANS
    return v


def record_start(hwnd: int) -> None:
    u32.keybd_event(VK_RMENU, 0, EXT, None)
    u32.PostMessageW(hwnd, WM_KEYDOWN, ctypes.c_void_p(VK_RMENU), ctypes.c_void_p(ralt_lp(True)))


def record_stop(hwnd: int) -> None:
    u32.PostMessageW(hwnd, WM_KEYUP, ctypes.c_void_p(VK_RMENU), ctypes.c_void_p(ralt_lp(False)))
    u32.keybd_event(VK_RMENU, 0, EXT | UP, None)

# 音色 → 自报家门用的文本（英文名照念）
ITEMS = [
    ("冰糖", "我是冰糖，喂，能听到吗？"),
    ("茉莉", "我是茉莉，喂，能听到吗？"),
    ("苏打", "我是苏打，喂，能听到吗？"),
    ("白桦", "我是白桦，喂，能听到吗？"),
    ("Mia", "我是 Mia，喂，能听到吗？"),
    ("Chloe", "我是 Chloe，喂，能听到吗？"),
    ("Milo", "我是 Milo，喂，能听到吗？"),
    ("Dean", "我是 Dean，喂，能听到吗？"),
    ("mimo_default", "我是默认音色，喂，能听到吗？"),
]


def find_wechat():
    h = u32.FindWindowW(None, "微信")
    return int(h) if h else None


def focus_wechat(hwnd: int) -> bool:
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)
        time.sleep(0.35)
    for _ in range(3):
        d = wintypes.DWORD()
        tid = u32.GetWindowThreadProcessId(hwnd, ctypes.byref(d))
        cur = k32.GetCurrentThreadId()
        u32.AttachThreadInput(cur, tid, True)
        u32.SetForegroundWindow(hwnd)
        u32.AttachThreadInput(cur, tid, False)
        time.sleep(0.4)
        if int(u32.GetForegroundWindow() or 0) == hwnd:
            return True
        u32.ShowWindow(hwnd, 6)
        time.sleep(0.25)
        u32.ShowWindow(hwnd, 9)
        time.sleep(0.4)
        if int(u32.GetForegroundWindow() or 0) == hwnd:
            return True
    return False


def click_input():
    u32.SetCursorPos(INPUT_X, INPUT_Y)
    time.sleep(0.12)
    u32.mouse_event(0x0002, 0, 0, 0, None)
    time.sleep(0.05)
    u32.mouse_event(0x0004, 0, 0, 0, None)
    time.sleep(0.3)


def pick_pid():
    try:
        procs = frida.get_local_device().enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    for p in procs:
        if "weixin" in (p.name or "").lower():
            return p.pid
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--items", default="", help="JSON 文件：[{voice,text,style}]，用于自定义台词与情绪")
    ap.add_argument("--gap", type=float, default=1.3)
    ap.add_argument("--max-hold", type=float, default=20.0)
    args = ap.parse_args()

    from tts import synthesize_pcm, TTSError

    # items: (voice, text, style, model, wav)  —— wav 非空时直接发这个文件，跳过 TTS
    if args.items:
        import json as _json
        raw_items = _json.loads(Path(args.items).read_text(encoding="utf-8"))
        items = []
        for d in raw_items:
            wav = d.get("wav")
            text = d.get("text") or (Path(wav).stem if wav else "")
            items.append((d.get("voice") or "冰糖", text, d.get("style"),
                          d.get("model"), wav))
    else:
        items = [(v, t, None, None, None) for v, t in ITEMS]

    if args.only.strip():
        want = {s.strip() for s in args.only.split(",")}
        items = [it for it in items if it[0] in want]
    if not items:
        print("没有匹配的音色")
        return 1

    pid = pick_pid()
    if not pid:
        print("找不到 Weixin 进程")
        return 1
    print("attach pid=%d, 共 %d 条" % (pid, len(items)))
    session = frida.attach(pid)
    script = session.create_script(JS)
    script.on("message", lambda m, d: None)
    script.load()
    ex = getattr(script, "exports_sync", None) or script.exports

    hwnd = find_wechat()
    if not hwnd:
        print("找不到微信窗口")
        session.detach()
        return 1

    ok_count = 0
    for idx, (voice, text, style, model, wav) in enumerate(items, 1):
        label = text if len(text) <= 28 else text[:28] + "…"
        if wav:
            tag = "wav:" + Path(wav).stem
        else:
            tag = (model or "mimo-v2.5-tts") + ("/" + voice if "voicedesign" not in (model or "") else "")
        print("\n[%d/%d] %s  「%s」" % (idx, len(items), tag, label))
        try:
            if wav:
                from tts import to_wechat_pcm, load_config
                src = Path(wav)
                if not src.exists():
                    print("   文件不存在，跳过: %s" % src)
                    continue
                out_dir = Path((load_config().get("output") or {}).get("pcm_dir")
                               or r"<PROJECT_ROOT>\tmp")
                pcm = to_wechat_pcm(src.read_bytes(), out_dir / (src.stem + "_wx.pcm"))
            else:
                pcm = synthesize_pcm(text, voice=voice, style=style, model=model)
        except TTSError as exc:
            print("   TTS 失败，跳过: %s" % exc)
            continue
        raw_len = pcm.stat().st_size
        expect = raw_len // 2
        print("   PCM %.2fs (%d samples)" % (expect / 16000.0, expect))

        n = ex.loadfile(str(pcm))
        if int(n or 0) != expect:
            print("   载入样本数不符 (%s != %s)，跳过" % (n, expect))
            continue

        ex.arm()
        fg_before = u32.GetForegroundWindow()
        record_start(hwnd)          # 不切前台：真按 Alt + 给微信投递消息
        t1 = time.time()
        done = False
        while time.time() - t1 < args.max_hold:
            time.sleep(0.03)
            pr = ex.progress()
            if pr["cursor"] >= pr["total"] and pr["total"] > 0:
                done = True
                break
        record_stop(hwnd)
        st = ex.disarm()
        verdict = "OK" if done else "未喂完"
        stolen = "前台被抢!" if u32.GetForegroundWindow() != fg_before else "前台未变"
        print("   %s  按住 %.2fs  fed %d/%d  calls=%d  %s" % (
            verdict, time.time() - t1, st["cursor"], st["total"], st["calls"], stolen))
        if done:
            ok_count += 1
        time.sleep(args.gap)

    session.detach()
    print("\n完成：%d/%d 条已发出" % (ok_count, len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
