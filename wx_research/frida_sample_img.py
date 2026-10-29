"""hook 图片 XML 构造器 (Weixin.dll + 0x21806A0)，采样真实图片消息结构体。

用法:
    python frida_sample_img.py [pid] [seconds] [maxhits]

用户手动发送一张图片时捕获：
  - rdi 结构体（源图片消息体）按已知偏移解析出的字段
    （cdn url / aeskey / 尺寸 / md5 / filekey）
  - 调用栈，用于回溯上游「发送图片」入口

磁盘侧字段偏移来自静态逆向（图片 XML 构造器 rdi）：
    +0x160 to/from 字符串
    +0x180 imgsourceurl            (cap@+0x198)
    +0x1c0 cdnbigimgurl            (cap@+0x1d8)
    +0x1e0 hdlength                (int)
    +0x1e8 cdnmidimgurl            (cap@+0x200)
    +0x20c hevc_mid_size           (int)
    +0x210 cdnthumburl             (cap@+0x228)
    +0x230 cdnthumbaeskey          (cap@+0x248)
    +0x250 cdnthumblength          (int)
    +0x254 cdnthumbwidth           (int)
    +0x258 cdnthumbheight          (int)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

IMGXML_RVA = 0x21806A0
OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) {
    send({kind: 'fatal', err: 'Weixin.dll not loaded'});
} else {
    var base = MOD.base;
    var target = base.add(0x21806a0);
    send({kind: 'armed', base: base.toString(), target: target.toString()});

    function rdStr(p, off) {
        try {
            var cap = p.add(off + 0x18).readU64().toNumber();
            var len = p.add(off + 0x10).readU64().toNumber();
            if (!len || len <= 0 || len > 8192) return null;
            var ptr = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
            return ptr.readUtf8String(len);
        } catch (e) { return '<err ' + e + '>'; }
    }
    function rdInt(p, off) {
        try { return p.add(off).readU32(); } catch (e) { return null; }
    }

    var STR_FIELDS = [['to_or_from', 0x160], ['imgsourceurl', 0x180],
                      ['cdnbigimgurl', 0x1c0], ['cdnmidimgurl', 0x1e8],
                      ['cdnthumburl', 0x210], ['cdnthumbaeskey', 0x230]];
    var INT_FIELDS = [['hdlength', 0x1e0], ['hevc_mid_size', 0x20c],
                      ['cdnthumblength', 0x250], ['cdnthumbwidth', 0x254],
                      ['cdnthumbheight', 0x258]];

    var hits = 0;
    Interceptor.attach(target, {
        onEnter: function (args) {
            var self = args[0];
            var rec = {kind: 'imgxml', self: self.toString(),
                       fields: {}, ints: {}, bt: []};
            for (var i = 0; i < STR_FIELDS.length; i++)
                rec.fields[STR_FIELDS[i][0]] = rdStr(self, STR_FIELDS[i][1]);
            for (var j = 0; j < INT_FIELDS.length; j++)
                rec.ints[INT_FIELDS[j][0]] = rdInt(self, INT_FIELDS[j][1]);
            try {
                var fr = Thread.backtrace(this.context, Backtracer.ACCURATE);
                for (var k = 0; k < fr.length && k < 12; k++)
                    rec.bt.push(fr[k].sub(base).toString());
            } catch (e) { rec.bt = ['<err ' + e + '>']; }
            hits++;
            rec.hit = hits;
            send(rec);
        }
    });
}
"""


def pick_pid(explicit=None):
    device = frida.get_local_device()
    if explicit:
        return int(explicit)
    procs = [p for p in device.enumerate_processes() if "weixin" in p.name.lower()]
    # 加载了 Weixin.dll 的才是主进程，用最大的 pid 优先试探
    for p in sorted(procs, key=lambda x: -x.pid):
        try:
            s = frida.attach(p.pid)
            ok = {"v": False}
            sc = s.create_script(
                "var m=Process.findModuleByName('Weixin.dll');"
                "send({v: m!==null});")
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
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    maxhits = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，挂载图片 XML 构造器 hook，最长 {seconds}s / 最多 {maxhits} 次命中")

    session = frida.attach(pid)
    state = {"armed": False, "records": [], "fatal": None}

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:400], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            state["armed"] = True
            print(f"ARMED base={d['base']} target={d['target']}", flush=True)
        elif k == "fatal":
            state["fatal"] = d.get("err")
            print("FATAL:", d.get("err"), flush=True)
        elif k == "imgxml":
            state["records"].append(d)
            print(f"--- 命中 #{d.get('hit')} self={d['self']} ---", flush=True)
            for name, val in d.get("fields", {}).items():
                print(f"    {name:<16} = {val!r}", flush=True)
            for name, val in d.get("ints", {}).items():
                print(f"    {name:<16} = {val}", flush=True)
            print(f"    backtrace(rva): {d.get('bt')}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    if not state["armed"] and not state["fatal"]:
        print("hook 未确认挂载，请检查")
        return 2

    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if len(state["records"]) >= maxhits:
                break
    except KeyboardInterrupt:
        pass
    finally:
        out = OUT_DIR / "imgxml_sample.json"
        out.write_text(json.dumps(state["records"], ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n共 {len(state['records'])} 次命中，写入 {out}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
