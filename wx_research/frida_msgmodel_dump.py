"""Dump the message-model objects handed to WeChat's pack routine 0x160EBE0.

Why: wxb_send_text works by fabricating a "message model" (vtable 0x805E4E8)
and handing it to 0x160EBE0. The same routine is reached by the native sticker
path (0x160DF80 -> 0xDB40 + 0x160EBE0). If we can see the *real* message model
for a text send and for a sticker send side by side, the differing fields give
us the exact sticker model layout without guessing.

Signature observed in commit_160ebe0.asm:
    rcx -> object whose +0x08 / +0x10 are vector<shared_ptr<Model>> begin/end
    rdx -> task config produced by 0xDB40

Usage:
    python frida_msgmodel_dump.py [seconds]
Writes reports/msgmodel_dump.json (appended).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

DLL = "Weixin.dll"
OUT = Path(r"<PROJECT_ROOT>\reports\msgmodel_dump.json")
PACK = 0x160EBE0
DB40 = 0xDB40
MAX_OBJ = 0x900
MAX_RECORDS = 40

SESSION_JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const PACK = base.add(0x160EBE0);
const DB40 = base.add(0xDB40);
const MAX_OBJ = 0x900;
const MAX_RECORDS = 40;
const out = [];

function hexBytes(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n)))
            .map(b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) {
        return null;
    }
}

function safePtr(p) {
    try { return p.isNull() ? null : p.toString(); } catch (e) { return null; }
}

// count entries of vector<shared_ptr> where each element is 16 bytes
function readVector(begin, end) {
    const res = [];
    if (begin.isNull() || end.isNull()) return res;
    const count = end.sub(begin).toInt32() / 16;
    if (count < 0 || count > 64) return res;
    for (let i = 0; i < count; i++) {
        const el = begin.add(i * 16);
        let ptr = null, rep = null;
        try { ptr = el.readPointer(); } catch (e) {}
        try { rep = el.add(8).readPointer(); } catch (e) {}
        let vt = null;
        if (ptr && !ptr.isNull()) {
            try { vt = "0x" + ptr.readPointer().sub(base).toString(16); } catch (e) {}
        }
        res.push({ ptr: safePtr(ptr), rep: safePtr(rep), vtable_rva: vt,
                   hex: ptr && !ptr.isNull() ? hexBytes(ptr, MAX_OBJ) : null });
    }
    return res;
}

Interceptor.attach(PACK, {
    onEnter(args) {
        if (out.length >= MAX_RECORDS) return;
        const rcx = args[0], rdx = args[1];
        let begin = null, end = null, first = null;
        try { begin = rcx.add(8).readPointer(); } catch (e) {}
        try { end = rcx.add(0x10).readPointer(); } catch (e) {}
        try { first = rcx.readPointer(); } catch (e) {}
        let cfg_vt = null, cfg_hex = null;
        try {
            const v = rdx.readPointer();
            if (!v.isNull()) cfg_vt = "0x" + v.sub(base).toString(16);
        } catch (e) {}
        cfg_hex = hexBytes(rdx, 0xF0);

        const rec = {
            tid: Process.getCurrentThreadId(),
            rcx_0: safePtr(first),
            models: readVector(begin, end),
            cfg_vt: cfg_vt,
            cfg_hex: cfg_hex
        };
        out.push(rec);
        send({ tag: "rec", data: rec });
    }
});
"""


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name == "Weixin.exe"]
    if not procs:
        print("Weixin.exe not running")
        return 1
    pid = procs[0].pid
    print(f"attach pid={pid}, collecting {seconds}s ...")

    session = frida.attach(pid)
    script = session.create_script(SESSION_JS)

    records: list[dict] = []

    def on_message(message, data):  # noqa: ANN001
        if message.get("type") == "send":
            payload = message.get("payload") or {}
            if payload.get("tag") == "rec":
                rec = payload.get("data") or {}
                records.append(rec)
                models = rec.get("models") or []
                vt = ", ".join(m.get("vtable_rva") or "?" for m in models)
                print(f"  tid={rec.get('tid')} models={len(models)} vt=[{vt}] "
                      f"cfg={rec.get('cfg_vt')}")
        elif message.get("type") == "error":
            print(f"  script error: {message.get('description')}")

    script.on("message", on_message)
    script.load()

    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(2.0)

    try:
        script.unload()
    except Exception:
        pass
    session.detach()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prev = []
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = []
    prev.extend(records)
    OUT.write_text(json.dumps(prev, indent=1), encoding="utf-8")
    print(f"captured {len(records)} records -> {OUT} (total {len(prev)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
