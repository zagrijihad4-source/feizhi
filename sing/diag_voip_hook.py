"""Check whether the voice-encode hook target exists in the running Weixin."""
import sys

import frida

PID = int(sys.argv[1]) if len(sys.argv) > 1 else 49968

JS = r"""
'use strict';
var out = {modules: [], found: null, exps: []};
Process.enumerateModules().forEach(function (m) {
    var n = (m.name || '').toLowerCase();
    if (n.indexOf('voip') >= 0 || n.indexOf('silk') >= 0 || n.indexOf('audio') >= 0) {
        out.modules.push({name: m.name, base: m.base.toString(), size: m.size});
    }
});
var voip = Process.findModuleByName('VoipEngine.dll');
if (voip) {
    ['SKP_Silk_SDK_Encode', 'SKP_Silk_SDK_Decode', 'SKP_Silk_SDK_Get_Encoder_Size'].forEach(function (fn) {
        var p = voip.findExportByName(fn);
        out.exps.push({fn: fn, addr: p ? p.toString() : null});
    });
    out.found = voip.base.toString();
}
send(out);
"""


def main():
    dev = frida.get_local_device()
    session = dev.attach(PID)
    done = {"got": False}

    def on_message(msg, data):
        if msg["type"] == "send":
            info = msg["payload"]
            print("voip modules:", len(info["modules"]))
            for m in info["modules"]:
                print("  ", m)
            print("VoipEngine base:", info["found"])
            for e in info["exps"]:
                print("   export %-28s %s" % (e["fn"], e["addr"]))
            done["got"] = True

    script = session.create_script(JS)
    script.on("message", on_message)
    script.load()
    import time
    for _ in range(50):
        if done["got"]:
            break
        time.sleep(0.1)
    if not done["got"]:
        print("no reply from agent")
    session.detach()


if __name__ == "__main__":
    main()
