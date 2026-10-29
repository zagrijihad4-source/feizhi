# -*- coding: utf-8 -*-
"""语音链路侦察 —— 观察微信录音时加载了什么模块、获取了什么函数。

背景：微信 4.1.9.23 首次支持 PC 端发语音（Alt 键）。
Weixin.dll 只静态导入 3 个 DLL，却内含 SILK 符号；VoipEngine.dll 导出了
SKP_Silk_SDK_Encode / VoiceOpus_Encode / StartRecord / StopRecord。
所以判断：录音相关的音频模块是**运行时 LoadLibrary + GetProcAddress** 拿到的。
本脚本就 hook 这两个点，按一次 Alt 录音即可看清整条链路。

用法：
    python frida_voice_recon.py [--seconds 150]
运行时在微信里按住 Alt 录一条语音并发出（松开发送）。脚本自动超时退出。

输出：<PROJECT_ROOT>\\tmp\\voice_recon.txt（同时打到控制台）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\tmp\voice_recon.txt")

JS = r"""
'use strict';

function exp(name) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
    try { return Module.findExportByName(null, name); } catch (e) {}
    return null;
}

var AUDIO_RE = /silk|voice|opus|record|audio|mic|mmdev|wasapi|amr|speex|aac/i;
var proc = Process.id;

function log(kind, name, extra) {
    send({ t: kind, pid: proc, name: name, extra: extra || '' });
}

Interceptor.attach(exp('LoadLibraryW'), {
    onEnter: function (a) { this.p = a[0]; },
    onLeave: function (r) {
        try {
            var n = this.p.readUtf16String();
            if (n) log('LoadLibraryW', n);
        } catch (e) {}
    }
});

Interceptor.attach(exp('LoadLibraryExW'), {
    onEnter: function (a) { this.p = a[0]; },
    onLeave: function (r) {
        try {
            var n = this.p.readUtf16String();
            if (n) log('LoadLibraryExW', n);
        } catch (e) {}
    }
});

Interceptor.attach(exp('LoadLibraryA'), {
    onEnter: function (a) { this.p = a[0]; },
    onLeave: function (r) {
        try {
            var n = this.p.readAnsiString();
            if (n) log('LoadLibraryA', n);
        } catch (e) {}
    }
});

// 决策点：拿到什么函数。过滤音频相关名，避免刷屏。
Interceptor.attach(exp('GetProcAddress'), {
    onEnter: function (a) {
        try { this.n = a[1].readAnsiString(); } catch (e) { this.n = null; }
    },
    onLeave: function (r) {
        if (this.n && AUDIO_RE.test(this.n)) {
            log('GetProcAddress', this.n, r.toString());
        }
    }
});

// 若音频模块此刻已经加载，直接把导出 hook 上，看谁被真正调用
var ALREADY_LOADED = ['VoipEngine.dll', 'mmdevapi.dll', 'audioses.dll', 'winmm.dll'];
var HOOK_NAMES = ['SKP_Silk_SDK_Encode', 'SKP_Silk_SDK_InitEncoder',
                  'VoiceOpus_Encode', 'VoiceOpus_Init',
                  'StartRecord', 'StopRecord', 'CreateEngineInstance'];

ALREADY_LOADED.forEach(function (m) {
    var mod = Process.findModuleByName(m);
    if (!mod) return;
    log('ModulePresent', m, mod.base.toString());
    HOOK_NAMES.forEach(function (fn) {
        var p = null;
        try { p = mod.findExportByName(fn); } catch (e) {}
        if (!p) return;
        try {
            Interceptor.attach(p, {
                onEnter: function () { log('CALLED', m + '!' + fn, Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 6).map(function (x) { return x.toString(); }).join(' <- ')); }
            });
            log('HookOK', m + '!' + fn, p.toString());
        } catch (e) { log('HookFAIL', m + '!' + fn, String(e)); }
    });
});

log('ready', 'pid=' + proc, 'modules=' + Process.enumerateModules().length);
"""


def pick_pids() -> list[tuple[int, str]]:
    try:
        dev = frida.get_local_device()
        procs = dev.enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    out = []
    for p in procs:
        if "weixin" in (p.name or "").lower():
            out.append((p.pid, p.name))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=150)
    args = ap.parse_args()

    targets = pick_pids()
    if not targets:
        print("没有找到 Weixin 进程")
        return 1

    lines: list[str] = []
    seen_loads: set = set()
    seen_calls: set = set()
    started = time.time()

    def emit(s: str) -> None:
        lines.append(s)
        print(s, flush=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")

    emit("=== 语音链路侦察 @ %s ===" % time.strftime("%H:%M:%S"))
    emit("目标进程: %s" % ", ".join("%s(%d)" % (n, p) for p, n in targets))
    emit("请在微信里按住 Alt 录一条语音并发出（松开发送）。%d 秒后自动结束。" % args.seconds)
    emit("")

    sessions = []
    for pid, name in targets:
        try:
            sess = frida.attach(pid)
            script = sess.create_script(JS)

            def on_message(msg, data, _name=name, _pid=pid):
                if msg.get("type") == "send":
                    p = msg["payload"]
                    kind = p.get("t")
                    if kind in ("LoadLibraryW", "LoadLibraryExW", "LoadLibraryA"):
                        nm = p["name"]
                        low = nm.lower()
                        # api-ms-win-* 是 API set 转发，空闲时也会反复加载，纯噪音
                        if low.startswith("api-ms-win-") or "downlevel" in low:
                            return
                        if ("system32" in low or "winsxs" in low) and \
                           not any(k in low for k in ("audio", "voice", "mmdev", "voip", "media")):
                            return
                        key = (_pid, low)
                        if key in seen_loads:
                            return
                        seen_loads.add(key)
                        emit("[%d] LOAD   %s  (%s)" % (_pid, nm, kind))
                    else:
                        extra = p.get("extra", "")
                        key = (_pid, p.get("name", ""), extra[:80])
                        if key in seen_calls:
                            return
                        seen_calls.add(key)
                        emit("[%d] %-16s %-36s %s" % (_pid, kind, p.get("name", ""), extra[:220]))

            script.on("message", on_message)
            script.load()
            sessions.append((sess, script))
        except Exception as exc:  # noqa: BLE001
            emit("[%d] attach 失败: %s" % (pid, exc))

    try:
        while time.time() - started < args.seconds:
            time.sleep(1)
    except KeyboardInterrupt:
        emit("\n(手动中断)")
    finally:
        for sess, _s in sessions:
            try:
                sess.detach()
            except Exception:
                pass

    emit("")
    emit("=== 结束 @ %s ===" % time.strftime("%H:%M:%S"))
    print("结果 -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
