"""Probe which WeChat internal functions are hit during real sends.

The previous script relied on frida's send() channel and captured nothing, so
this one writes hits straight to a file with frida's File API and hooks a fan of
candidate functions at once:

    0x16A60D0  send entry (native sticker path)
    0x160EBE0  pack (used by wxb_send_text)
    0xDB40     message task constructor
    0x1AFE710  envelope factory
    0x16D5B80  envelope factory #2
    0x17040A0  envelope ctor
    0x160DF80  emoji message constructor
    0x34F0A70  TaskContext ctor
    0x15F35C0  content ctor

Usage: python frida_probe_hits.py [seconds]
Output: reports/frida_hits.txt (truncated at start, appended per hit)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

HITS = Path(r"<PROJECT_ROOT>\reports\frida_hits.txt")
PACK_DUMP = Path(r"<PROJECT_ROOT>\reports\frida_pack_models.txt")

TARGETS = [
    (0x16A60D0, "send_entry"),
    (0x160EBE0, "pack"),
    (0xDB40, "db40"),
    (0x1AFE710, "env_factory"),
    (0x16D5B80, "env_factory2"),
    (0x17040A0, "env_ctor"),
    (0x160DF80, "emoji_ctor"),
    (0x34F0A70, "task_ctor"),
    (0x15F35C0, "content_ctor"),
]

SESSION_JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const HITS = "<PROJECT_ROOT>\\reports\\frida_hits.txt";
const PACKDUMP = "<PROJECT_ROOT>\\reports\\frida_pack_models.txt";

function log(line) {
    try {
        const f = new File(HITS, "a");
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

log("== script loaded, base=" + base.toString() + " ==");

const TARGETS = __TARGETS__;

TARGETS.forEach(function (t) {
    const addr = base.add(t[0]);
    try {
        Interceptor.attach(addr, {
            onEnter(args) {
                const tid = Process.getCurrentThreadId();
                let line = t[1] + " tid=" + tid +
                    " rcx=" + args[0] + " rdx=" + args[1] +
                    " r8=" + args[2] + " r9=" + args[3];
                if (t[1] === "pack") {
                    try {
                        const b = args[0].add(8).readPointer();
                        const e = args[0].add(0x10).readPointer();
                        const n = e.sub(b).toInt32() / 16;
                        line += " models=" + n;
                        let dump = "--- pack tid=" + tid + " models=" + n + "\n";
                        for (let i = 0; i < Math.min(n, 4); i++) {
                            const el = b.add(i * 16);
                            let p = null, vtr = "?";
                            try { p = el.readPointer(); } catch (er) {}
                            try { vtr = "0x" + p.readPointer().sub(base).toString(16); } catch (er) {}
                            dump += "  [" + i + "] vt=" + vtr + " hex=" +
                                    (p ? hexOf(p, 0x800) : "null") + "\n";
                        }
                        try {
                            const f = new File(PACKDUMP, "a");
                            f.write(dump);
                            f.flush();
                            f.close();
                        } catch (er) {}
                    } catch (er) {}
                }
                log(line);
            }
        });
        log("attached " + t[1] + " @ " + addr.toString());
    } catch (e) {
        log("attach FAILED " + t[1] + ": " + e);
    }
});
"""


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    HITS.parent.mkdir(parents=True, exist_ok=True)
    HITS.write_text("", encoding="utf-8")

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name == "Weixin.exe"]
    if not procs:
        print("Weixin.exe not running")
        return 1
    for p in procs:
        print(f"  candidate pid={p.pid}")
    pid = procs[0].pid
    print(f"attach pid={pid}, {seconds}s ...")

    js = SESSION_JS.replace("__TARGETS__", json.dumps(TARGETS))
    session = frida.attach(pid)
    script = session.create_script(js)

    def on_message(message, data):  # noqa: ANN001
        if message.get("type") == "error":
            print(f"  script error: {message.get('description')} @ {message.get('stack')}")

    script.on("message", on_message)
    script.load()

    deadline = time.time() + seconds
    last = 0
    while time.time() < deadline:
        time.sleep(2.0)
        try:
            n = len(HITS.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            n = 0
        if n != last:
            print(f"  hits file lines: {n}")
            last = n

    try:
        script.unload()
    except Exception:
        pass
    session.detach()
    print("done; see " + str(HITS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
