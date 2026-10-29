"""在发送提交点 dump 消息对象（含子对象）—— 深挖到消息内容。

第一版只 dump 前 0x300 字节，结果只看到 vtable + 自指针 + 接收方 wxid。
析构函数 0x1704220 暴露了对象真实深度：它会 release [rcx+0x678] 与 [rsi+0x668]
两个 shared_ptr，说明对象至少 0x680 字节，内容在那两个子对象里。

本版：
  - dump 整个 0x700 字节
  - 跟随 +0x668 / +0x678 指向的子对象，各自 dump 0x400
  - 字符串扫描覆盖全范围
  - stdout 只打印摘要，完整 hex 落 JSON

用法:
    python frida_msg_dump2.py [pid] [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'Weixin.dll not loaded'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

  function hexdump(p, n) {
    try {
      var u8 = new Uint8Array(p.readByteArray(n));
      var s = '';
      for (var i = 0; i < u8.length; i++) {
        var h = u8[i].toString(16);
        if (h.length < 2) h = '0' + h;
        s += h;
        if ((i + 1) % 32 === 0) s += '\n';
      }
      return s;
    } catch (e) { return ''; }
  }

  function scanStrings(p, size) {
    var out = [];
    for (var off = 0; off + 0x20 <= size; off += 8) {
      try {
        var len = p.add(off + 0x10).readU64().toNumber();
        var cap = p.add(off + 0x18).readU64().toNumber();
        if (!(len > 0 && len < 4096 && cap >= len && cap <= 0x40000)) continue;
        var sp = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
        var s = sp.readUtf8String(len);
        if (s && /^[\x20-\x7e\u4e00-\u9fff\u3000-\u303f]+$/.test(s))
          out.push({off: off, len: len, cap: cap, s: s});
      } catch (e) {}
    }
    return out;
  }

  function snapshot(p, size) {
    var o = {ptr: p.toString(), vt: null, strs: [], hex: ''};
    try { o.vt = p.readPointer().toString(); } catch (e) {}
    try { o.strs = scanStrings(p, size); } catch (e) {}
    try { o.hex = hexdump(p, size); } catch (e) {}
    return o;
  }

  var n = 0;
  Interceptor.attach(base.add(0x160ebe0), {
    onEnter: function (args) {
      if (n >= 6) return;
      n++;
      var rcxs = args[0];
      var rec = {kind:'commit', n: n, rcxs: rcxs.toString(), objs: []};
      try {
        var begin = rcxs.add(8).readPointer();
        var end = rcxs.add(0x10).readPointer();
        var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
        rec.count = cnt;
        if (cnt > 0 && cnt < 64) {
          for (var i = 0; i < cnt; i++) {
            var obj = begin.add(i * 16).readPointer();
            if (obj.isNull()) continue;
            var o = snapshot(obj, 0x700);
            o.idx = i;
            o.subs = [];
            [0x668, 0x678].forEach(function (soff) {
              try {
                var sp = obj.add(soff).readPointer();
                if (sp.isNull()) return;
                var sub = snapshot(sp, 0x400);
                sub.via = soff;
                o.subs.push(sub);
              } catch (e) {}
            });
            rec.objs.push(o);
          }
        }
      } catch (e) { rec.err = '' + e; }
      send(rec);
    }
  });
  send({kind:'hooked', name:'send_commit @ 0x160ebe0'});
}
"""


def pick_pid(explicit=None):
    device = frida.get_local_device()
    if explicit:
        return int(explicit)
    for p in sorted([p for p in device.enumerate_processes() if "weixin" in p.name.lower()],
                    key=lambda x: -x.pid):
        try:
            s = frida.attach(p.pid)
            ok = {"v": False}
            sc = s.create_script("var m=Process.findModuleByName('Weixin.dll');send({v:m!==null});")
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，深度 dump 消息对象+子对象，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "msg_dump2.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def summarize(o, indent="    "):
        print(f"{indent}obj {o['ptr']} vt={o['vt']}", flush=True)
        for s in o.get("strs", []):
            print(f"{indent}  +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s'][:120]!r}", flush=True)
        for sub in o.get("subs", []) or []:
            print(f"{indent}  子对象 via+{sub['via']:#x} {sub['ptr']} vt={sub['vt']}", flush=True)
            for s in sub.get("strs", []):
                print(f"{indent}    +{s['off']:#05x} len={s['len']:<5} {s['s'][:120]!r}", flush=True)

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k in ("armed", "hooked", "fatal"):
            print(f"  {k}: {d.get('base') or d.get('name') or d.get('err')}", flush=True)
            return
        records.append(d)
        flush()
        print(f"\n########## 提交 #{d.get('n')} 消息数={d.get('count')} ##########", flush=True)
        if d.get("err"):
            print(f"  遍历失败: {d['err']}", flush=True)
        for o in d.get("objs", []):
            summarize(o)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪，等待发送操作 ...", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n共 {len(records)} 次提交，写入 {OUT_DIR / 'msg_dump2.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
