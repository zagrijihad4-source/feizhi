"""抓取「微信自己发图片」时的完整对象链。

目的：
  前面手工构造图片消息失败了三次（都崩），根因是套用了 aixed（4.1.10.27）
  的字段布局与 vtable，而本机是 4.1.9.23。这次改为从真实运行中取数据：
  让你手动发一张图，我把微信自己构造并提交的对象完整 dump 下来，
  再照着它构造 —— 不再猜。

同时挂两个点做交叉印证：
  0x160ebe0  发送提交 —— 参数 rcxs 是消息容器（[+8]=begin,[+0x10]=end，
             元素 16 字节 shared_ptr），可遍历出真正被提交的消息对象
  0x21806a0  图片 XML 构造函数 —— 参数 rdi 是图片消息体
             （已知字段: +0x160 aeskey / +0x1c0 cdnbigimgurl / +0x210 cdnthumburl …）

用法:
    python frida_img_capture.py [pid] [seconds]
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
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

  var MAX = 6;
  var counts = {};

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

  function guard(k, maxv) {
    counts[k] = counts[k] || 0;
    if (counts[k] >= (maxv || MAX)) return false;
    counts[k]++;
    return true;
  }

  // ---- 提交点：dump 真正被提交的消息对象 ----
  try {
    Interceptor.attach(base.add(0x160ebe0), {
      onEnter: function (args) {
        if (!guard('commit')) return;
        var rcxs = args[0];
        var rec = {kind:'commit', rcxs: rcxs.toString(), result: args[1].toString(),
                   objs: [], rcxs_hex: hexdump(rcxs, 0x40)};
        try {
          var begin = rcxs.add(8).readPointer();
          var end = rcxs.add(0x10).readPointer();
          var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
          rec.count = cnt;
          for (var i = 0; i < cnt && i < 4; i++) {
            var elem = begin.add(i * 16);
            var obj = elem.readPointer();
            if (obj.isNull()) continue;
            var o = {idx: i, elem_ptr: obj.toString(),
                     elem_ctrl: elem.add(8).readPointer().toString(),
                     vt: obj.readPointer().toString(),
                     strs: scanStrings(obj, 0x800),
                     hex: hexdump(obj, 0x300)};
            // 跟随 +0x668 / +0x678 子对象（表情消息形状）
            o.subs = [];
            [0x668, 0x678].forEach(function (so) {
              try {
                var sp = obj.add(so).readPointer();
                if (sp.isNull()) return;
                o.subs.push({via: so, ptr: sp.toString(),
                             vt: sp.readPointer().toString(),
                             strs: scanStrings(sp, 0x400)});
              } catch (e) {}
            });
            rec.objs.push(o);
          }
        } catch (e) { rec.err = '' + e; }
        send(rec);
      }
    });
    send({kind:'hooked', name:'commit @0x160ebe0'});
  } catch (e) { send({kind:'hookfail', name:'commit', err:''+e}); }

  // ---- 图片消息体（XML 构造函数的 this）----
  try {
    Interceptor.attach(base.add(0x21806a0), {
      onEnter: function (args) {
        if (!guard('imgbody')) return;
        var self = args[0];
        send({kind:'imgbody', self: self.toString(),
              vt: (function(){ try { return self.readPointer().toString(); } catch(e){ return null; } })(),
              strs: scanStrings(self, 0x400),
              hex: hexdump(self, 0x300)});
      }
    });
    send({kind:'hooked', name:'imgbody @0x21806a0'});
  } catch (e) { send({kind:'hookfail', name:'imgbody', err:''+e}); }
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
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，抓取发图对象链，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "img_capture.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k in ("armed", "hooked", "hookfail", "fatal"):
            print(f"  {k}: {d.get('name') or d.get('base') or d.get('err')}", flush=True)
            return
        records.append(d)
        flush()
        if k == "commit":
            print(f"\n=== [COMMIT] rcxs={d['rcxs']} result={d['result']} 消息数={d.get('count')} ===", flush=True)
            if d.get("err"):
                print(f"  遍历失败: {d['err']}", flush=True)
            for o in d.get("objs", []):
                print(f"  --- 消息[{o['idx']}] ptr={o['elem_ptr']} ctrl={o['elem_ctrl']} vtable={o['vt']} ---", flush=True)
                for s in o.get("strs", []):
                    print(f"      +{s['off']:#05x} len={s['len']:<5} {s['s'][:110]!r}", flush=True)
                for sub in o.get("subs", []):
                    print(f"      子对象 via+{sub['via']:#x} {sub['ptr']} vt={sub['vt']}", flush=True)
                    for s in sub.get("strs", []):
                        print(f"        +{s['off']:#05x} {s['s'][:110]!r}", flush=True)
        elif k == "imgbody":
            print(f"\n=== [IMGBODY] self={d['self']} vtable={d.get('vt')} ===", flush=True)
            for s in d.get("strs", []):
                print(f"      +{s['off']:#05x} len={s['len']:<5} {s['s'][:110]!r}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请发一张图片（发给文件传输助手即可）", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if len([r for r in records if r.get("kind") == "commit"]) >= 2:
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n共 {len(records)} 条记录，写入 {OUT_DIR / 'img_capture.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
