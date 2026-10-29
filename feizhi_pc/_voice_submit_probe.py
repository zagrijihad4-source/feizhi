# -*- coding: utf-8 -*-
r"""侦察：语音消息（type 34）到底经不经过 pack 提交点 0x160EBE0。

为什么查这个：
  多用户化的死结是「语音只能发给当前打开的会话」。文档已经把结构讲明白了：
  所有消息模型 body 坐标 +0xB0 是接收方 wxid，而 0x160EBE0 是文本/表情共用的
  pack 提交点。如果语音也走这里，就能照常让微信录音、编码、上传，
  **只在提交前把 receiver 换成目标 wxid** —— 不点任何东西、不碰 CDN。

  这和收藏表情的「载体替换」（TASK_LOG §26）是同一条路，那条已经验证过。

本脚本只观察、不写任何字节：
  装 hook -> 调 voice.say 真发一条 -> 把经过提交点的每个模型打印出来
  重点看 +0xD8 类型码、+0xB0 的 wxid、以及 +0x160 那带里有没有 voicemsg XML

用法：
    python _voice_submit_probe.py [--no-send]
"""
import ctypes
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import frida  # noqa: E402

PEER = "<WXID_FRIEND_A>"

JS = r'''
'use strict';
const base = Process.getModuleByName('Weixin.dll').base;
const w = (m) => send({ t: 'log', m: m });

function rva(p) {
    try { return '0x' + p.sub(base).toString(16); } catch (e) { return '?'; }
}

// std::string 读法（与 frida_sticker_swap.py 一致）
function readStr(obj, off) {
    const out = { len: 0, cap: 0, txt: '' };
    try {
        out.len = obj.add(off + 0x10).readInt();
        out.cap = obj.add(off + 0x18).readInt();
        if (out.len > 0 && out.len < 4096) {
            const buf = (out.cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
            if (!buf.isNull()) out.txt = buf.readUtf8String(out.len);
        }
    } catch (e) { out.txt = '<ERR ' + e + '>'; }
    return out;
}

let packs = 0;
Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        try {
            const b = args[0].add(8).readPointer();
            const e = args[0].add(0x10).readPointer();
            const n = e.sub(b).toInt32() / 16;
            if (n <= 0 || n > 32) return;
            packs++;
            let s = 'PACK#' + packs + ' models=' + n;
            for (let i = 0; i < Math.min(n, 4); i++) {
                let m;
                try { m = b.add(i * 16).readPointer(); } catch (e1) { continue; }
                let vt = '?';
                try { vt = rva(m.readPointer()); } catch (e2) { continue; }
                const recv = readStr(m, 0xB0);
                let type = '?', d0 = '?', e0 = '?';
                try { type = m.add(0xD8).readInt(); } catch (e3) {}
                try { d0 = m.add(0xD0).readInt(); } catch (e4) {}
                try { e0 = m.add(0xE0).readInt(); } catch (e5) {}
                s += '\n  model' + i + ' vt=' + vt +
                     ' type(+0xD8)=' + type + ' +0xD0=' + d0 + ' +0xE0=' + e0 +
                     '\n    receiver len=' + recv.len + ' cap=' + recv.cap +
                     ' : ' + recv.txt;
                // 类型 34 = 语音；顺手把内容区几种可能的位置都看一眼
                if (type === 34 || recv.txt) {
                    [0x160, 0x180, 0x660].forEach(function (off) {
                        try {
                            const p = m.add(off).readPointer();
                            if (p.isNull()) return;
                            let svt = '?';
                            try { svt = rva(p.readPointer()); } catch (x) {}
                            s += '\n    +' + off.toString(16) + ' -> ' + p +
                                 ' vt=' + svt;
                        } catch (x) {}
                    });
                }
            }
            w(s);
        } catch (err) { w('PACK ERR ' + err); }
    }
});
w('probe attached at 0x160EBE0, base=' + base.toString());
'''


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import voice

    pid = voice._pick_pid()
    print("weixin pid =", pid, " hwnd =", voice.find_wechat_window())

    session = frida.attach(pid)
    script = session.create_script(JS)
    logs: list[str] = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            p = msg.get("payload") or {}
            if p.get("t") == "log":
                print(p["m"], flush=True)
                logs.append(p["m"])
        else:
            print("[frida]", msg, flush=True)

    script.on("message", on_msg)
    script.load()
    time.sleep(0.8)

    if "--no-send" not in sys.argv:
        print("\n--- 真发一条语音，观察提交点 ---")
        ok = voice.say("这句是用来观察提交路径的", "温柔", PEER)
        print("say ->", ok)
        time.sleep(1.5)

    script.unload()
    session.detach()

    print("\n" + "=" * 70)
    print("共经过 %d 次 pack 提交" % len([x for x in logs if x.startswith("PACK#")]))
    hit34 = [x for x in logs if "type(+0xD8)=34" in x]
    print("其中 type=34（语音）的提交：%d 次" % len(hit34))
    for h in hit34:
        print(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
