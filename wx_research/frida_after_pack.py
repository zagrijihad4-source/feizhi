"""Trace what happens AFTER pack (0x160EBE0) for our submitted message.

Rationale: cfg, envelope and content are now byte-comparable with the native
path, yet the message still reports "send failed". So the divergence must be
downstream of pack. 0x290390 (the delivery call inside pack) returns the output
pointer with no error code, so we follow the chain instead:

  0x262100   scheduler that runs a std::function task
  0x8E07B0   send logic (virtual, this-adjust thunk seen in the native trace)
  0x1B6A700  task function that posts a send
  0x83D5D0   task poster (calls 0x25C590)
  0x1AFE710  envelope factory (sticker path)

Each hit logs registers + a shallow backtrace, written to
reports/frida_after_pack.txt, so we can tell whether OUR message reaches the
processing chain at all.

Usage: python frida_after_pack.py [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_after_pack.txt")

TARGETS = [
    # Distinct functions only -- never two interior points of one function.
    (0x28F2F0, "ENQUEUE"),        # real queueing call made by 0x290390
    (0x28EF10, "ENQUEUE_PATH_A"), # taken when check on r8 passes
    (0xC13360, "ENQUEUE_CHECK"),  # predicate over r8+8
]

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_after_pack.txt";
const TARGETS = __TARGETS__;
const counters = {};

function w(line) {
    try {
        const f = new File(OUT, "a");
        f.write(line + "\n");
        f.flush();
        f.close();
    } catch (e) {}
}

function rva(p) {
    try { return "0x" + p.sub(base).toString(16); } catch (e) { return "?"; }
}

w("== after-pack probe loaded base=" + base.toString() + " ==");

TARGETS.forEach(function (t) {
    const name = t[1];
    counters[name] = 0;
    try {
        Interceptor.attach(base.add(t[0]), {
            onEnter(args) {
                this.argv = [args[0].toString(), args[1].toString(),
                             args[2].toString(), args[3].toString()].join(",");
                this.tid = Process.getCurrentThreadId();
                try {
                    this.bt = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 8).map(a => rva(a)).join(" < ");
                } catch (e) { this.bt = "?"; }
            },
            onLeave(retval) {
                if (counters[name]++ > 60) return;
                w(name + " tid=" + this.tid + " ret=" + rval(retval) +
                  " args=" + this.argv + "\n  bt: " + this.bt + "\n");
            }
        });
        w("attached " + name);
    } catch (e) {
        w("attach " + name + " FAILED " + e);
    }
});

function rval(v) {
    try { return "" + v; } catch (e) { return "?"; }
}
"""


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
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
    script = session.create_script(JS.replace("__TARGETS__", json.dumps(TARGETS)))

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
