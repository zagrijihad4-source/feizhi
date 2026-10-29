"""Read objects directly at absolute addresses captured earlier in this session.

Why: the delegate captures recorded by frida_cfg_dump.py show that both the
text-group and the envelope-group delegates capture the SAME two heap pointers
(0x2d1fa8d8ea0 and 0x2d1fa91c6e0). That means they are long-lived shared
objects, not per-message context -- and since the WeChat process has not been
restarted, we can read them now without asking for another send.

Usage:
    python frida_read_addrs.py <hexaddr> [<hexaddr> ...]
Defaults to the two captured pointers.
Output: reports/frida_addrs.txt
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_addrs.txt")
DEFAULT = ["2d1fa8d8ea0", "2d1fa91c6e0", "2d1fb22cf70"]

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_addrs.txt";
const ADDRS = __ADDRS__;

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

w("== addr read, base=" + base.toString() + " ==");
ADDRS.forEach(function (a) {
    const p = ptr(a.indexOf("0x") === 0 ? a : "0x" + a);
    let s = "ADDR " + a + " vt=" + rva(p.readPointer()) + "\n";
    s += "  hex0x100=" + hexOf(p, 0x100) + "\n";
    // If this looks like a content object (vtable 0x8755528), resolve its 12
    // std::string slots so a FRESH template can be built from live memory.
    try {
        if (rva(p.readPointer()) === "0x8755528") {
            for (let k = 0; k < 12; k++) {
                const off = 0x10 + k * 0x20;
                let len = 0, cap = 0, txt = "";
                try {
                    len = p.add(off + 0x10).readInt();
                    cap = p.add(off + 0x18).readInt();
                    if (len > 0 && len < 8192) {
                        if (cap <= 0xF) {
                            txt = p.add(off).readUtf8String(len);
                        } else {
                            const bp = p.add(off).readPointer();
                            if (!bp.isNull()) txt = bp.readUtf8String(len);
                        }
                    }
                } catch (e7) {}
                s += "  slot" + k + " len=" + len + " cap=0x" + cap.toString(16) +
                     (txt ? " : " + txt : " : (empty)") + "\n";
            }
        }
    } catch (e8) { s += "  slot resolve ERR " + e8 + "\n"; }
    // follow the first few pointer-looking qwords one hop
    for (let k = 0; k < 0x80; k += 8) {
        try {
            const v = p.add(k).readPointer();
            if (v.compare(ptr("0x10000")) > 0 && v.compare(ptr("0x7fffffffffff")) < 0) {
                const inner = hexOf(v, 0x40);
                if (inner !== "ERR") {
                    s += "  +0x" + k.toString(16) + " -> " + v +
                         " vt=" + rva(v.readPointer()) + " hex=" + inner + "\n";
                }
            }
        } catch (e) {}
    }
    w(s);
});
w("done");
"""


def main() -> int:
    addrs = sys.argv[1:] or DEFAULT
    addrs = [a[2:] if a.startswith("0x") else a for a in addrs]
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
    print(f"attach pid={pid}; reading {len(addrs)} addresses")
    session = frida.attach(pid)
    script = session.create_script(JS.replace("__ADDRS__", json.dumps(addrs)))

    def on_message(message, data):  # noqa: ANN001
        if message.get("type") == "error":
            print("  script error:", message.get("description"))

    script.on("message", on_message)
    script.load()
    time.sleep(4)
    try:
        script.unload()
    except Exception:
        pass
    session.detach()
    print(OUT.read_text(encoding="utf-8", errors="replace")[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
