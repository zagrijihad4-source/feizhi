"""Capture deep call stacks of WeChat's sticker send path.

Goal: walk from emoji_ctor (0x160DF80) outwards to the UI/dispatch layer, so we
can find the layer whose parameters are simple enough to synthesize
(session + sticker identity) instead of the internal task context.

Hooks:
  0x160DF80  emoji_ctor            (innermost, confirmed)
  0x1AFD280  upper layer
  0x8E07B0   send logic (virtual, this-adjust thunk)
  0x83D5D0   task poster (calls 0x25C590)
  0x262100   scheduler
Each hit logs a 24-frame backtrace plus the four register arguments.

Usage: python frida_deep_stack.py [seconds]
Output: reports/frida_stack.txt
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_stack.txt")

TARGETS = [
    (0x160DF80, "emoji_ctor"),
    (0x1AFD280, "layer_1afd280"),
    (0x8E07B0, "send_logic"),
    (0x83D5D0, "task_poster"),
    (0x262100, "scheduler"),
]

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_stack.txt";
const TARGETS = __TARGETS__;
const seen = {};

function log(line) {
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

function bt(ctx, n) {
    try {
        return Thread.backtrace(ctx, Backtracer.ACCURATE)
            .slice(0, n).map(a => rva(a));
    } catch (e) { return ["ERR"]; }
}

log("== deep stack loaded base=" + base.toString() + " ==");

TARGETS.forEach(function (t) {
    const key = t[1];
    seen[key] = 0;
    try {
        Interceptor.attach(base.add(t[0]), {
            onEnter(args) {
                seen[key]++;
                if (seen[key] > 12) return;
                const tid = Process.getCurrentThreadId();
                let s = "HIT " + t[1] + " tid=" + tid +
                        " rcx=" + args[0] + " rdx=" + args[1] +
                        " r8=" + args[2] + " r9=" + args[3] + "\n";
                const stack = bt(this.context, 24);
                s += "  bt: " + stack.join(" < ") + "\n";
                // if rdx looks like a std::function, its first qword is the vtable
                try {
                    const v = args[1].readPointer();
                    if (!v.isNull()) s += "  rdx->vt=" + rva(v) + "\n";
                } catch (e) {}
                log(s);
            }
        });
    } catch (e) {
        log("attach FAILED " + key + " " + e);
    }
});
log("all attached");
"""


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 180
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
