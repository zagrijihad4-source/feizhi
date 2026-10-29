"""Capture everything handed to pack (0x160EBE0) so the task config can be
compared between WeChat's native send and ours.

Already proven equal: envelope model (vtable 0x82CB8D8) and content object
strings. Still unknown: the 2nd argument (rdx), i.e. the config produced by
0xDB40, and the container object's own header.

Usage: python frida_cfg_dump.py [seconds]
Output: reports/frida_cfg.txt
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_cfg.txt")

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_cfg.txt";

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

w("== cfg dump loaded base=" + base.toString() + " ==");

Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        const tid = Process.getCurrentThreadId();
        let s = "PACK tid=" + tid + "\n";
        s += "  container_hex=" + hexOf(args[0], 0x80) + "\n";
        s += "  cfg_hex=" + hexOf(args[1], 0xF0) + "\n";
        // The three std::function delegates live inside cfg. 0xDB40 stores the
        // data pointer of each at +0x48 / +0x88 / +0xC8. At pack time the owning
        // stack frame is still alive, so those pointers can be dereferenced now.
        const cfg = args[1];
        // Layout 0xDB40 produces: delegate #1 @+0x10, #2 @+0x50, #3 @+0x90
        // (0x40 bytes each, self/data pointer at +0x38 within each block).
        // Dumping the CFG side is what actually proves whether an injected
        // [A,B,A] capture reached the config -- the earlier dumps only showed
        // the *input* delegates handed to 0xDB40.
        try {
            for (let d = 0; d < 3; d++) {
                const off = 0x10 + d * 0x40;
                s += "  cfg_d" + (d + 1) + "_hex=" + hexOf(cfg.add(off), 0x40) + "\n";
            }
            s += "  cfg_tail_hex=" + hexOf(cfg.add(0xd0), 0x20) + "\n";
        } catch (e9) { s += "  cfg delegate dump ERR " + e9 + "\n"; }
        // The 5th argument of 0xDB40 becomes cfg[0]/cfg[8] (a shared_ptr).
        // WeChat's native path passes a real object there; we passed NULL, which
        // is why the envelope delegate group crashed. Dump it.
        try {
            const p5 = cfg.readPointer();
            const rep = cfg.add(8).readPointer();
            s += "  p5_ptr=" + p5 + " p5_rep=" + rep + "\n";
            if (!p5.isNull()) {
                s += "    p5_body_hex=" + hexOf(p5, 0x40) + "\n";
                // body[0] is a plain pointer (not a vtable): follow it one hop.
                try {
                    const inner = p5.readPointer();
                    if (!inner.isNull()) {
                        s += "    p5_body0=" + inner +
                             " vt=" + rva(inner.readPointer()) +
                             " hex=" + hexOf(inner, 0x100) + "\n";
                        try {
                            const inner2 = inner.readPointer();
                            if (!inner2.isNull()) {
                                s += "      lvl2=" + inner2 +
                                     " vt=" + rva(inner2.readPointer()) +
                                     " hex=" + hexOf(inner2, 0x80) + "\n";
                            }
                        } catch (e3) {}
                    }
                } catch (e2) { s += "    p5_body0 ERR " + e2 + "\n"; }
            }
            if (!rep.isNull()) {
                s += "    p5_ctrl_vt=" + rva(rep.readPointer()) +
                     " hex=" + hexOf(rep, 0x40) + "\n";
            }
        } catch (e) { s += "  p5 dump ERR " + e + "\n"; }
        [["d1", 0x48], ["d2", 0x88], ["d3", 0xc8]].forEach(function (p) {
            try {
                const dp = cfg.add(p[1]).readPointer();
                s += "  " + p[0] + "_data_ptr=0x" + dp.toString(16) +
                     " hex=" + hexOf(dp, 0x100) + "\n";
                // one more hop: most delegates capture an object pointer
                for (let k = 0; k < 0x100; k += 8) {
                    try {
                        const v = dp.add(k).readPointer();
                        if (v.compare(ptr("0x10000")) > 0 &&
                            v.compare(ptr("0x7fffffffffff")) < 0) {
                            const inner = hexOf(v, 0x80);
                            if (inner !== "ERR") {
                                s += "    " + p[0] + "+0x" + k.toString(16) +
                                     " -> " + v + " : " + inner + "\n";
                            }
                        }
                    } catch (e) {}
                }
            } catch (e) { s += "  " + p[0] + "_data_ptr ERR " + e + "\n"; }
        });
        try {
            const b = args[0].add(8).readPointer();
            const e = args[0].add(0x10).readPointer();
            const n = e.sub(b).toInt32() / 16;
            s += "  models=" + n + "\n";
            for (let i = 0; i < Math.min(n, 2); i++) {
                const p = b.add(i * 16).readPointer();
                s += "  model" + i + "_vt=" + rva(p.readPointer()) +
                     " hex=" + hexOf(p, 0x100) + "\n";
                // The image message model keeps a content object at +0xE0
                // (body coordinates; block+0xF0). +0xE8 is zero, which is why
                // the previous probe silently skipped it.
                try {
                    const c = p.add(0xE0).readPointer();
                    if (!c.isNull()) {
                        s += "    model" + i + "_+0xE0=" + c +
                             " vt=" + rva(c.readPointer()) +
                             " hex=" + hexOf(c, 0x120) + "\n";
                        try {
                            const c1 = c.readPointer();
                            if (!c1.isNull()) {
                                s += "      +0xE0->0 vt=" + rva(c1.readPointer()) +
                                     " hex=" + hexOf(c1, 0x80) + "\n";
                            }
                        } catch (e4) {}
                    }
                } catch (e5) { s += "    model" + i + "_+0xE0 ERR " + e5 + "\n"; }
                // The sticker envelope keeps its Content object at +0x660/+0x668.
                // Dumping it gives a freshly captured template (CDN filekeys in the
                // old template set may have expired, which would explain a send
                // that reaches WeChat but fails).
                try {
                    const cb = p.add(0x660).readPointer();
                    if (!cb.isNull()) {
                        s += "    model" + i + "_+0x660=" + cb +
                             " vt=" + rva(cb.readPointer()) +
                             " hex=" + hexOf(cb, 0x1B0) + "\n";
                        // Resolve the 12 std::string slots so the template can be
                        // replayed with FRESH cdn filekeys (the captured set from
                        // hours ago may have expired).
                        for (let k = 0; k < 12; k++) {
                            const off = 0x10 + k * 0x20;
                            let len = 0, cap = 0, txt = "";
                            try {
                                len = cb.add(off + 0x10).readInt();
                                cap = cb.add(off + 0x18).readInt();
                                if (len > 0 && len < 8192) {
                                    if (cap <= 0xF) {
                                        txt = cb.add(off).readUtf8String(len);
                                    } else {
                                        const bp = cb.add(off).readPointer();
                                        if (!bp.isNull()) txt = bp.readUtf8String(len);
                                    }
                                }
                            } catch (e7) {}
                            if (txt) s += "      slot" + k + " len=" + len +
                                          " cap=0x" + cap.toString(16) +
                                          " : " + txt + "\n";
                        }
                    }
                } catch (e6) { s += "    model" + i + "_+0x660 ERR " + e6 + "\n"; }
            }
        } catch (er) { s += "  err " + er + "\n"; }
        w(s);
    }
});
w("attached pack");

// 0xDB40 takes six arguments (rcx/rdx/r8/r9 + two stack slots). Our own
// wxb_send_sticker_pack only passes five, so record the native shape to settle
// what the 5th/6th arguments really are and which delegate group is used.
const seenDb40 = new Set();
Interceptor.attach(base.add(0xDB40), {
    onEnter(args) {
        const tid = Process.getCurrentThreadId();
        const key = [args[0], args[1], args[2], args[3], args[4], args[5]].join("|");
        if (seenDb40.has(key) || seenDb40.size > 300) return;
        seenDb40.add(key);
        let s = "DB40 tid=" + tid +
                " p1=" + args[0] + " p2=" + args[1] + " p3=" + args[2] +
                " p4=" + args[3] + " p5=" + args[4] + " p6=" + args[5] + "\n";
        [["d1", args[1]], ["d2", args[2]], ["d3", args[3]]].forEach(function (d) {
            try {
                const p = d[1];
                const vt = rva(p.readPointer());
                const self = p.add(0x38).readPointer();
                s += "    " + d[0] + " vt=" + vt + " self=" + self +
                     " self_hex=" + hexOf(self, 0x20) + "\n";
            } catch (e) { s += "    " + d[0] + " ERR " + e + "\n"; }
        });
        w(s);
    }
});
w("attached db40");

// Which factory does the sticker chain actually touch? 0x1702E50 initialises the
// IMAGE message model; 0x1AFE710 creates the sticker ENVELOPE. Recording both
// settles whether image-model reuse is even reachable for stickers.
[[0x1702E50, "CTOR_IMG_MODEL"], [0x1AFE710, "FACTORY_ENVELOPE"]].forEach(function (t) {
    const seen = new Set();
    try {
        Interceptor.attach(base.add(t[0]), {
            onEnter(args) {
                const tid = Process.getCurrentThreadId();
                const key = args[0] + "|" + args[1];
                if (seen.has(key) || seen.size > 200) return;
                seen.add(key);
                let s = t[1] + " tid=" + tid +
                        " rcx=" + args[0] + " rdx=" + args[1] +
                        " r8=" + args[2] + " r9=" + args[3] + "\n";
                try {
                    s += "  bt: " + Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .slice(0, 10).map(a => rva(a)).join(" < ") + "\n";
                } catch (e) {}
                w(s);
            }
        });
        w("attached " + t[1]);
    } catch (e) {
        w("attach " + t[1] + " FAILED " + e);
    }
});

// 0x290390 is the delivery call at the very end of pack (0x160EBE0).
// Recording its result helps locate the first failing branch, rather than
// attributing "send failed" to session validation without evidence.
let deliverCount = 0;
Interceptor.attach(base.add(0x290390), {
    onEnter(args) {
        this.tid = Process.getCurrentThreadId();
        this.argv = [args[0].toString(), args[1].toString(),
                     args[2].toString(), args[3].toString()].join(",");
    },
    onLeave(retval) {
        if (deliverCount++ > 200) return;
        w("DELIVER 0x290390 tid=" + this.tid + " ret=" + retval +
          " args=" + this.argv + "\n");
    }
});
w("attached deliver 290390");
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
            print("  script error:", message.get("description"))

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
