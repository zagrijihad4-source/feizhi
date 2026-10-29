"""Deep dump of WeChat's own sticker send path.

Findings so far:
  * We CAN reach pack (0x160EBE0) and our envelope is field-identical to
    WeChat's own (vtable 0x82CB8D8), yet nothing arrives at the recipient.
  * So the missing piece is either (a) the Content object inside the envelope,
    or (b) the extra work 0x160DF80 (emoji_ctor) does around pack.

This script captures, on the native path:
  * 0x160DF80 entry: rcx context (0x200 bytes), [rcx+0x38] container (0x100),
    and a backtrace to identify the caller
  * 0x160EBE0 pack: each model (0x800 bytes) plus its +0x660 Content object
    (0x1B0 bytes)

Usage: python frida_deep_dump.py [seconds]
Output: reports/frida_deep.txt
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_deep.txt")

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_deep.txt";

function w(line) {
    try {
        const f = new File(OUT, "a");
        f.write(line + "\n");
        f.flush();
        f.close();
    } catch (e) {}
}

function hexOf(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n)))
            .map(b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) { return "ERR"; }
}

function rva(p) {
    try { return "0x" + p.sub(base).toString(16); } catch (e) { return "?"; }
}

function bt(ctx) {
    try {
        return Thread.backtrace(ctx, Backtracer.ACCURATE)
            .slice(0, 8).map(a => rva(a)).join(" < ");
    } catch (e) { return "ERR"; }
}

w("== deep dump loaded, base=" + base.toString() + " ==");

// ---- emoji_ctor 0x160DF80 ----
try {
    Interceptor.attach(base.add(0x160DF80), {
        onEnter(args) {
            const tid = Process.getCurrentThreadId();
            let s = "EMOJI_CTOR tid=" + tid +
                    " rcx=" + args[0] + " rdx=" + args[1] +
                    " r8=" + args[2] + " r9=" + args[3] + "\n";
            s += "  bt: " + bt(this.context) + "\n";
            s += "  ctx+0x000: " + hexOf(args[0], 0x120) + "\n";
            try {
                const c = args[0].add(0x38).readPointer();
                if (!c.isNull()) {
                    s += "  ctx[+0x38]=" + c + " vtable=" + rva(c.readPointer()) + "\n";
                    s += "  ctx[+0x38]+0x000: " + hexOf(c, 0x120) + "\n";
                }
            } catch (e) {}
            w(s);
        }
    });
    w("attached emoji_ctor");
} catch (e) { w("attach emoji_ctor FAILED " + e); }

// ---- pack 0x160EBE0 ----
try {
    Interceptor.attach(base.add(0x160EBE0), {
        onEnter(args) {
            const tid = Process.getCurrentThreadId();
            let s = "PACK tid=" + tid + " rcx=" + args[0] + " rdx=" + args[1] + "\n";
            try {
                const b = args[0].add(8).readPointer();
                const e = args[0].add(0x10).readPointer();
                const n = e.sub(b).toInt32() / 16;
                s += "  models=" + n + "\n";
                for (let i = 0; i < Math.min(n, 2); i++) {
                    const el = b.add(i * 16);
                    const p = el.readPointer();
                    const rep = el.add(8).readPointer();
                    s += "  [" + i + "] ptr=" + p + " rep=" + rep +
                         " vt=" + rva(p.readPointer()) + "\n";
                    s += "    model: " + hexOf(p, 0x700) + "\n";
                    // content object held at model+0x660 / +0x668
                    try {
                        const cb = p.add(0x660).readPointer();
                        if (!cb.isNull()) {
                            s += "    content vt=" + rva(cb.readPointer()) + "\n";
                            s += "    content: " + hexOf(cb, 0x1B0) + "\n";
                        }
                    } catch (er) {}
                }
            } catch (er) { s += "  dump err " + er + "\n"; }
            w(s);
        }
    });
    w("attached pack");
} catch (e) { w("attach pack FAILED " + e); }
"""


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("", encoding="utf-8")

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name == "Weixin.exe"]
    if not procs:
        print("Weixin.exe not running")
        return 1
    pid = procs[0].pid
    print(f"attach pid={pid}, {seconds}s ...")

    session = frida.attach(pid)
    script = session.create_script(JS)

    def on_message(message, data):  # noqa: ANN001
        if message.get("type") == "error":
            print(f"  script error: {message.get('description')}")

    script.on("message", on_message)
    script.load()

    deadline = time.time() + seconds
    last = 0
    while time.time() < deadline:
        time.sleep(2.0)
        try:
            n = len(OUT.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            n = 0
        if n != last:
            print(f"  lines: {n}")
            last = n

    try:
        script.unload()
    except Exception:
        pass
    session.detach()
    print("done ->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
