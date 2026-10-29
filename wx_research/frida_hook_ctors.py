"""Hook every message-model initializer discovered by find_vtable_loaders.py.

Context: the text message model works end-to-end through pack(). Its vtable is
0x805E578, set inside 0x6A35B0. Adjacent functions 0x6A0860 / 0x6A0F20 / ...
each set a different vtable from the same .rdata window, i.e. one per message
type. Hooking them all identifies which initializer corresponds to a sticker/
emoji message, purely by observing a real send.

Usage: python frida_hook_ctors.py [seconds]
Output: reports/frida_ctors.txt
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\reports\frida_ctors.txt")

ENTRIES = [
    0x6A03A0, 0x6A0860, 0x6A0F20, 0x6A11C0, 0x6A1460, 0x6A15B0, 0x6A1A60,
    0x6A2380, 0x6A2CB0, 0x6A35B0, 0x6A36B0, 0x6A3C70, 0x6A4650, 0x6A4A70,
    0x6A4DF0, 0x6A5780, 0x6A6320, 0x6A64D0, 0x6A6610, 0x6A6760, 0x6A68B0,
    0x6A6D70, 0x6A7370, 0x6A74D0, 0x6A95E0, 0x6A9AA0, 0x6AA1C0, 0x6AAC50,
]

JS = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\frida_ctors.txt";
const ENTRIES = __ENTRIES__;

function log(line) {
    try {
        const f = new File(OUT, "a");
        f.write(line + "\n");
        f.flush();
        f.close();
    } catch (e) {}
}

log("== ctor hooks loaded base=" + base.toString() + " count=" + ENTRIES.length + " ==");

ENTRIES.forEach(function (rva) {
    try {
        Interceptor.attach(base.add(rva), {
            onEnter(args) {
                log("CTOR 0x" + rva.toString(16) +
                    " tid=" + Process.getCurrentThreadId() +
                    " rcx=" + args[0] + " rdx=" + args[1] + " r8=" + args[2]);
            }
        });
    } catch (e) {
        log("attach FAILED 0x" + rva.toString(16) + " " + e);
    }
});
log("all attached");
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
    script = session.create_script(JS.replace("__ENTRIES__", json.dumps(ENTRIES)))

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
