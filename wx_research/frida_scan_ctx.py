"""扫描定位发送任务上下文 —— 验证它是否是可以"捡起来就用"的持久单例。

动机
----
§27 的免点击方案依赖「先捕获一次自然发送的上下文」。但如果该对象是进程级单例
（两次实验里同一进程内捕获到的地址始终相同），那就完全不必依赖捕获——
直接扫描定位即可，**连那一次点击都不需要**。

判据
----
控制块 ctrl 的 vtable RVA = 0x7f5f398（§20.5 实测值，§27 用作存活判据）。
扫内存找「某地址处存的 8 字节 == base + 0x7f5f398」，命中处即候选 ctrl，
其对象体 body = ctrl + 0x10。

本脚本只读内存，不做任何写入、不 hook 任何函数。
用法: python frida_scan_ctx.py
"""
from __future__ import annotations

import sys

import frida

CTRL_VT_RVA = 0x7F5F398

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const want = base.add(__RVA__);

function w(line) {
    try { send({ line: line }); } catch (e) {}
}

function rva(p) {
    try { return "0x" + p.sub(base).toString(16); } catch (e) { return "?"; }
}

function hexOf(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n)))
            .map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    } catch (e) { return "ERR"; }
}

function ptrPattern(p) {
    const s = p.toString(16).padStart(16, "0");
    const out = [];
    for (let i = 14; i >= 0; i -= 2) out.push(s.substr(i, 2));
    return out.join(" ");
}

w("base=" + base.toString() + " want_ctrl_vt=" + want.toString() + " (RVA 0x" +
  (__RVA__).toString(16) + ")");
w("pattern=" + ptrPattern(want));

const pat = ptrPattern(want);
let total = 0;
const ranges = Process.enumerateRanges("rw-");
w("rw- ranges=" + ranges.length);

ranges.forEach(function (r) {
    if (r.file) return;                       // 只看匿名私有内存（堆）
    if (r.size < 0x1000) return;
    let found = [];
    try {
        found = Memory.scanSync(r.base, r.size, pat);
    } catch (e) {
        return;
    }
    found.forEach(function (m) {
        total++;
        const ctrl = m.address;
        const body = ctrl.add(0x10);
        let line = "HIT#" + total + " ctrl=" + ctrl + " (rva " + rva(ctrl) + ")" +
                   " body=" + body;
        try {
            const uses = ctrl.add(8).readInt();
            const weaks = ctrl.add(0xc).readInt();
            line += " uses=" + uses + " weaks=" + weaks;
        } catch (e) {}
        w(line);
        try {
            w("   body[0..0x60]=" + hexOf(body, 0x60));
            const b0 = body.readPointer();
            w("   body[0]=" + b0 + " rva=" + rva(b0) +
              (b0.isNull() ? "" : " ->[0]=" + hexOf(b0, 0x40)));
            if (!b0.isNull()) {
                const b1 = b0.readPointer();
                w("   body[0][0]=" + b1 + " ->" + (b1.isNull() ? "" : hexOf(b1, 0x40)));
            }
        } catch (e) { w("   body dump ERR " + e); }
    });
});
w("TOTAL_HITS=" + total);
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name.lower() == "weixin.exe"]
    if not procs:
        print("Weixin.exe 未运行")
        return 1

    for p in procs:
        try:
            session = frida.attach(p.pid)
        except Exception as e:  # noqa: BLE001
            continue
        script = session.create_script(JS.replace("__RVA__", hex(CTRL_VT_RVA)))
        lines: list[str] = []

        def on_msg(message, data):  # noqa: ANN001, ARG001
            if message.get("type") == "send":
                lines.append((message.get("payload") or {}).get("line", ""))
            elif message.get("type") == "error":
                lines.append("script error: " + str(message.get("description")))

        script.on("message", on_msg)
        try:
            script.load()
        except Exception as e:  # noqa: BLE001
            print(f"pid={p.pid} load 失败: {e}")
            session.detach()
            continue

        import time  # noqa: PLC0415
        time.sleep(6.0)
        if lines:
            print(f"=== pid={p.pid} ===")
            for ln in lines:
                print(ln)
        try:
            script.unload()
        except Exception:
            pass
        session.detach()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
