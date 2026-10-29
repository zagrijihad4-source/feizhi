"""表情包表情的载体替换 —— 验证「点一个、发另一个」。

与 frida_sticker_swap.py 的区别
------------------------------
那个脚本用于**收藏表情**：内容对象的 slot0/2/6/7/8/9 分别装 md5 与三条 CDN URL，
就地覆写 6 个槽。本节针对**表情包（表情商店添加）**表情，其布局不同（实测）：
    收藏表情：  +0x08 = 3，slot0/2/6/7/8/9 有值（含 3 条 vweixinf CDN URL）
    表情包表情：+0x08 = 5，slot0 = 该表情 md5，slot1 = 专辑 ID
                `com.tencent.xin.emoticon.person.stiker_<…>`（同专辑内所有表情相同）
                其余槽全空，不带任何 CDN URL（地址由微信自己解析）

因此本脚本只改 **slot0**（32 字符，cap 通常 0x2f=47），把载体的表情换成目标表情。
slot1（专辑 ID）保持不变——同一专辑内两枚表情的 slot1 实测逐字节相同。

判定
----
你点表情包里的任意一枚，对端若收到**另一枚**，即证明「程序可发送任意表情包表情」。

用法
----
    python frida_pack_sticker_swap.py                # dry-run
    python frida_pack_sticker_swap.py --live         # 真替换
    python frida_pack_sticker_swap.py --live --seconds 900
输出: reports/frida_pack_swap_<pid>.txt
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

REPORTS = Path(r"<PROJECT_ROOT>\reports")

# 实测采集到的同专辑两枚表情（reports/collected_templates.json）
MEMBERS = [
    {"md5": "1b09ef505de4501c4f77569207864e4b", "label": "表情包成员 A"},
    {"md5": "a6d3a7abb8d7084bff4540c7e5676184", "label": "表情包成员 B"},
]

VT_STICKER_ENVELOPE = "0x82cb8d8"
VT_CONTENT_BODY = "0x8755528"
ALBUM_ID_PREFIX = "com.tencent.xin.emoticon.person.stiker_"

JS_TEMPLATE = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = __OUT__;
const MEMBERS = __MEMBERS__;
const LIVE = __LIVE__;
const MAX_SWAPS = __MAX_SWAPS__;
const VT_ENV = "__VT_ENV__";
const VT_BODY = "__VT_BODY__";
const ALBUM_PREFIX = "__ALBUM__";

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

function readSlot(obj, slot) {
    const off = 0x10 + slot * 0x20;
    let len = 0, cap = 0, txt = "";
    try {
        len = obj.add(off + 0x10).readInt();
        cap = obj.add(off + 0x18).readInt();
        if (len > 0 && len < 8192) {
            const buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
            if (!buf.isNull()) txt = buf.readUtf8String(len);
        }
    } catch (e) {}
    return { len: len, cap: cap, txt: txt };
}

function writeSlot(obj, slot, text) {
    const off = 0x10 + slot * 0x20;
    let cap = 0;
    try { cap = obj.add(off + 0x18).readInt(); } catch (e) { return "CAP_ERR"; }
    if (text.length > cap) return "NO_ROOM(len=" + text.length + " cap=" + cap + ")";
    let buf = null;
    try {
        buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
    } catch (e) { return "BUF_ERR"; }
    if (buf === null || buf.isNull()) return "NULL_BUF";
    try {
        buf.writeUtf8String(text);
        buf.add(text.length).writeU8(0);
        obj.add(off + 0x10).writeInt(text.length);
    } catch (e) { return "WRITE_ERR " + e; }
    return "OK";
}

let packHits = 0, swaps = 0;

w("== pack-sticker swap loaded base=" + base.toString() + " live=" + LIVE + " ==");

setInterval(function () {
    w("TICK packHits=" + packHits + " swaps=" + swaps);
}, 5000);

Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        packHits++;
        try {
            const b = args[0].add(8).readPointer();
            const e = args[0].add(0x10).readPointer();
            const n = e.sub(b).toInt32() / 16;
            if (n <= 0 || n > 8) return;
            const m = b.readPointer();
            if (rva(m.readPointer()) !== VT_ENV) return;
            const cb = m.add(0x660).readPointer();
            if (cb.isNull() || rva(cb.readPointer()) !== VT_BODY) return;

            const s0 = readSlot(cb, 0);
            const s1 = readSlot(cb, 1);
            const plus08 = cb.add(8).readInt();
            let s = "PACK#" + packHits + " tid=" + Process.getCurrentThreadId() + "\n";
            s += "  +0x08=" + plus08 + " slot0=" + s0.txt + " (len=" + s0.len +
                 " cap=" + s0.cap + ")\n";
            s += "  slot1=" + s1.txt.substring(0, 80) + " (len=" + s1.len + ")\n";

            // 只处理「表情包型」：slot1 是专辑 ID
            if (s1.txt.indexOf(ALBUM_PREFIX) !== 0) {
                s += "  跳过：不是表情包表情（slot1 非专辑 ID）\n";
                w(s);
                return;
            }

            // 目标选择：载体在表内 → 换成相邻成员；载体不在表内（同专辑的其它成员，
            // 例如本次的 ebd98e27「稍等」）→ 直接换成表内第一枚。
            // 不做「必须在成员表内」的拦截：专辑 ID 已经保证了类型正确，
            // 同专辑内任意两枚的 slot0 都是 32 字符、cap 0x2f，覆写恒安全。
            let cur = -1;
            for (let i = 0; i < MEMBERS.length; i++) {
                if (MEMBERS[i].md5 === s0.txt) { cur = i; break; }
            }
            const tgt = (cur < 0) ? 0 : (cur + 1) % MEMBERS.length;
            const curLabel = (cur < 0) ? "同专辑其它成员（不在成员表内）"
                                       : MEMBERS[cur].label;
            s += "  载体 " + curLabel + " md5=" + s0.txt +
                 "  ->  目标 [" + tgt + "] " + MEMBERS[tgt].label +
                 " md5=" + MEMBERS[tgt].md5 + "\n";
            if (s0.txt === MEMBERS[tgt].md5) {
                s += "  跳过：载体与目标相同\n";
                w(s);
                return;
            }

            if (!LIVE) { s += "  DRY-RUN：未写入\n"; w(s); return; }
            if (swaps >= MAX_SWAPS) { s += "  已达替换上限\n"; w(s); return; }

            // 只改 slot0：两枚 md5 都是 32 字符，cap 足够，零重分配
            const r = writeSlot(cb, 0, MEMBERS[tgt].md5);
            s += "  write slot0 -> " + r + "\n";
            const after = readSlot(cb, 0);
            s += "  after slot0 = " + after.txt + " (len=" + after.len + ")\n";
            if (r === "OK") {
                swaps++;
                s += "  SWAP#" + swaps + " 完成\n";
                send({ hit: "swapped", target: MEMBERS[tgt].md5 });
            }
            w(s);
        } catch (err) { w("PACK ERR " + err); }
    }
});
w("attached pack 0x160EBE0");
"""


def build_js(out_path: Path, live: bool, max_swaps: int) -> str:
    js = JS_TEMPLATE
    js = js.replace("__OUT__", json.dumps(str(out_path)))
    js = js.replace("__MEMBERS__", json.dumps(MEMBERS, ensure_ascii=False))
    js = js.replace("__LIVE__", "true" if live else "false")
    js = js.replace("__MAX_SWAPS__", str(max_swaps))
    js = js.replace("__VT_ENV__", VT_STICKER_ENVELOPE)
    js = js.replace("__VT_BODY__", VT_CONTENT_BODY)
    js = js.replace("__ALBUM__", ALBUM_ID_PREFIX)
    return js


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    argv = sys.argv[1:]
    live = "--live" in argv
    seconds = 900
    max_swaps = 1
    for i, a in enumerate(argv):
        if a == "--seconds" and i + 1 < len(argv):
            seconds = int(argv[i + 1])
        elif a == "--max-swaps" and i + 1 < len(argv):
            max_swaps = int(argv[i + 1])

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name.lower() == "weixin.exe"]
    if not procs:
        print("Weixin.exe 未运行")
        return 1

    print(f"模式: {'LIVE 写入' if live else 'DRY-RUN 只观察'} | "
          f"成员表: {[m['md5'][:8] for m in MEMBERS]}")

    sessions = []
    hits = set()
    for p in procs:
        out = REPORTS / f"frida_pack_swap_{p.pid}.txt"
        out.write_text("", encoding="utf-8")

        def make_handler(cur_pid):
            def handler(message, data):  # noqa: ANN001, ARG001
                if message.get("type") == "error":
                    print(f"  [pid={cur_pid}] script error:", message.get("description"))
                elif message.get("type") == "send":
                    print(f"  [pid={cur_pid}] HIT {message.get('payload')}")
                    hits.add(cur_pid)
            return handler

        try:
            session = frida.attach(p.pid)
            script = session.create_script(build_js(out, live, max_swaps))
            script.on("message", make_handler(p.pid))
            script.load()
            sessions.append((p.pid, session, script, out))
            print(f"  已挂 pid={p.pid} -> {out.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  pid={p.pid} attach 失败: {e}")

    if not sessions:
        print("没有进程挂载成功")
        return 1

    print("\n>>> 请发送一个表情包表情（同专辑内任意一枚）")

    deadline = time.time() + seconds
    last = {pid: 0 for pid, _, _, _ in sessions}
    while time.time() < deadline:
        time.sleep(1.5)
        for pid, _, _, out in sessions:
            try:
                n = len(out.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                n = 0
            if n != last[pid]:
                last[pid] = n
        if hits:
            print("  已命中，结束等待")
            break

    for pid, session, script, _ in sessions:
        try:
            script.unload()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass

    print("\n== 结果 ==")
    for pid, _, _, out in sessions:
        txt = ""
        try:
            txt = out.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        lines = [ln for ln in txt.splitlines() if not ln.startswith("TICK")]
        if lines:
            print(f"--- {out.name} ---")
            print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
