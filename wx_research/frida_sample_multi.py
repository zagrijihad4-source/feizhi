"""多点 hook 采样：一次操作抓全微信图片消息的构造/解析/提交路径。

挂载点（RVA 相对 Weixin.dll，均已在运行时逐字节验证）：
    0x21806a0  图片 XML 构造器（vtable 槽 0，序列化 rdi 结构体）
    0xa19440   消息体解析器（23947 字节，含 cdnthumburl/emoticonmd5 字段解析）
    0x160ebe0  发送链最终提交（CALL3）

对每个命中：
  - 记录 this 指针与 backtrace（回溯上游入口）
  - 自动扫描 this 结构体，按 MSVC std::string 布局（buf@0/len@0x10/cap@0x18）
    发现所有字符串字段 —— 不依赖预判偏移，避免漏字段
  - 对图片结构中已知偏移额外做精确解析

用法:
    python frida_sample_multi.py [pid] [seconds] [maxhits]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

HOOKS = [
    ("imgxml_xml", 0x21806A0),   # 图片 XML 构造器
    ("msg_parser", 0xA19440),    # 消息体解析器
    ("send_commit", 0x160EBE0),  # 发送链提交
]

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

SCRIPT_TMPL = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) {
    send({kind: 'fatal', err: 'Weixin.dll not loaded'});
} else {
    var base = MOD.base;
    send({kind: 'armed', base: base.toString()});

    // MSVC std::string: buf[16]@+0, len@+0x10, cap@+0x18
    function scanStrings(p, size) {
        var out = [];
        for (var off = 0; off + 0x20 <= size; off += 8) {
            try {
                var len = p.add(off + 0x10).readU64().toNumber();
                var cap = p.add(off + 0x18).readU64().toNumber();
                if (!(len > 0 && len < 2048 && cap >= len && cap <= 0x20000))
                    continue;
                var sptr = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
                var s = sptr.readUtf8String(len);
                if (!s) continue;
                if (!/^[\x20-\x7e\u4e00-\u9fff\u3000-\u303f]+$/.test(s)) continue;
                out.push({off: off, len: len, cap: cap, s: s});
            } catch (e) { }
        }
        return out;
    }

    var STR_FIELDS = [['to_or_from', 0x160], ['imgsourceurl', 0x180],
                      ['cdnbigimgurl', 0x1c0], ['cdnmidimgurl', 0x1e8],
                      ['cdnthumburl', 0x210], ['cdnthumbaeskey', 0x230]];
    var INT_FIELDS = [['hdlength', 0x1e0], ['hevc_mid_size', 0x20c],
                      ['cdnthumblength', 0x250], ['cdnthumbwidth', 0x254],
                      ['cdnthumbheight', 0x258]];

    function rdStr(p, off) {
        try {
            var cap = p.add(off + 0x18).readU64().toNumber();
            var len = p.add(off + 0x10).readU64().toNumber();
            if (!(len > 0 && len < 8192)) return null;
            var ptr = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
            return ptr.readUtf8String(len);
        } catch (e) { return '<err>'; }
    }

    var HOOKS = __HOOKS__;
    HOOKS.forEach(function (h) {
        var counts = {n: 0};
        try {
            Interceptor.attach(base.add(h.rva), {
                onEnter: function (args) {
                    if (counts.n >= __MAXPER__) return;
                    counts.n++;
                    var self = args[0];
                    var rec = {kind: 'hit', hook: h.name, rva: h.rva,
                               self: self.toString(), n: counts.n,
                               bt: [], strs: [], fields: {}, ints: {}};
                    try {
                        var fr = Thread.backtrace(this.context, Backtracer.ACCURATE);
                        for (var k = 0; k < fr.length && k < 12; k++)
                            rec.bt.push(fr[k].sub(base).toString());
                    } catch (e) { rec.bt = ['<err>']; }
                    try { rec.strs = scanStrings(self, 0x400); } catch (e) {}
                    try {
                        for (var i = 0; i < STR_FIELDS.length; i++)
                            rec.fields[STR_FIELDS[i][0]] = rdStr(self, STR_FIELDS[i][1]);
                        for (var j = 0; j < INT_FIELDS.length; j++)
                            rec.ints[INT_FIELDS[j][0]] =
                                self.add(INT_FIELDS[j][1]).readU32();
                    } catch (e) {}
                    send(rec);
                }
            });
            send({kind: 'hooked', name: h.name, rva: h.rva});
        } catch (e) {
            send({kind: 'hookfail', name: h.name, err: '' + e});
        }
    });
}
"""


def pick_pid(explicit=None):
    device = frida.get_local_device()
    if explicit:
        return int(explicit)
    procs = [p for p in device.enumerate_processes() if "weixin" in p.name.lower()]
    for p in sorted(procs, key=lambda x: -x.pid):
        try:
            s = frida.attach(p.pid)
            ok = {"v": False}
            sc = s.create_script("var m=Process.findModuleByName('Weixin.dll');send({v: m!==null});")
            sc.on("message", lambda m, d: ok.__setitem__("v", m.get("payload", {}).get("v", False)))
            sc.load()
            time.sleep(0.6)
            s.detach()
            if ok["v"]:
                return p.pid
        except Exception:
            continue
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    pid = pick_pid(sys.argv[1] if len(sys.argv) > 1 else None)
    if not pid:
        print("找不到加载了 Weixin.dll 的微信进程")
        return 1
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    maxper = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    hooks_js = "[" + ",".join(
        f"{{name: {n!r}, rva: {r:#x}}}" for n, r in HOOKS) + "]"
    src = SCRIPT_TMPL.replace("__HOOKS__", hooks_js).replace("__MAXPER__", str(maxper))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，挂载 {len(HOOKS)} 个 hook，最长 {seconds}s，每点最多 {maxper} 次", flush=True)

    session = frida.attach(pid)
    state = {"records": [], "armed": False, "hooked": []}

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            state["armed"] = True
            print(f"ARMED base={d['base']}", flush=True)
        elif k == "hooked":
            state["hooked"].append(d["name"])
            print(f"  hooked {d['name']} @ {d['rva']:#x}", flush=True)
        elif k == "hookfail":
            print(f"  hook 失败 {d['name']}: {d['err']}", flush=True)
        elif k == "fatal":
            print("FATAL:", d["err"], flush=True)
        elif k == "hit":
            state["records"].append(d)
            # 即时落盘：进程被强杀时也要保住已捕获的数据
            try:
                (OUT_DIR / "multi_sample.json").write_text(
                    json.dumps(state["records"], ensure_ascii=False, indent=2),
                    encoding="utf-8")
                with (OUT_DIR / "multi_sample.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(d, ensure_ascii=False) + "\n")
            except Exception as e:
                print("  [落盘失败]", e, flush=True)
            print(f"\n=== [{d['hook']}] 第 {d['n']} 次  this={d['self']} ===", flush=True)
            for name, val in d.get("fields", {}).items():
                if val:
                    print(f"    {name:<16} = {val!r}", flush=True)
            ints = {k2: v for k2, v in d.get("ints", {}).items() if v not in (None, 0)}
            if ints:
                print(f"    尺寸字段: {ints}", flush=True)
            for s in d.get("strs", []):
                print(f"    +{s['off']:#05x} len={s['len']:<4} cap={s['cap']:<6} {s['s'][:110]!r}", flush=True)
            print(f"    backtrace(rva): {d.get('bt')}", flush=True)

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    if not state["armed"]:
        print("未 armed，退出")
        return 2

    print("\n已就绪，等待图片消息触发 ...", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        out = OUT_DIR / "multi_sample.json"
        out.write_text(json.dumps(state["records"], ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n共 {len(state['records'])} 条记录，写入 {out}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
