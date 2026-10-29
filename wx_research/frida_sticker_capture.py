"""抓取「微信自己发收藏表情」的完整构造链。

目标：把表情消息从"内容对象"到"信封"到"提交"的每一步都录下来，
      然后照它实现发送 —— 不再靠猜。

已定位的构造链（均为函数入口，已用 capstone+.pdata 验证）：
    0x15f35c0  内容对象构造  void f(shared_ptr<Content>* out)
               内部 operator new(0x70)：前 0x10 是 shared_ptr 控制块，
               对象体自 +0x10 起，vtable = 0x82bcc28
    0x17040a0  信封构造      void f(shared_ptr<Envelope>* out, shared_ptr<Content>* in)
               对象体 vtable = 0x82cb8d8
    0x160ebe0  提交          void f(rcxs, result)
               rcxs 的 vector 元素是 shared_ptr<Envelope>

内容对象的已知字段（来自此前 dump）：
    +0x020 md5          +0x060/+0x120/+0x3a0/+0x3e0 其它规格 md5
    +0x0e0/+0x100/+0x140/+0x2a0/+0x2c0/+0x300  CDN 下载链接
信封的已知字段：
    +0x0b0 接收方 wxid   +0x600 消息 UUID   +0x668 内容子对象(shared_ptr)

用法:
    python frida_sticker_capture.py [pid] [seconds]
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

  var MAX = 4;
  var counts = {};
  function guard(k) {
    counts[k] = counts[k] || 0;
    if (counts[k] >= MAX) return false;
    counts[k]++;
    return true;
  }

  function hexdump(p, n) {
    try {
      var u8 = new Uint8Array(p.readByteArray(n)); var s = '';
      for (var i = 0; i < u8.length; i++) {
        var h = u8[i].toString(16); if (h.length < 2) h = '0' + h;
        s += h; if ((i + 1) % 32 === 0) s += '\n';
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

  function dumpSp(spPtr, label, size) {
    var o = {label: label, sp: spPtr.toString(), ptr: null, ctrl: null, vt: null,
             strs: [], hex: ''};
    try {
      o.ptr = spPtr.readPointer().toString();
      o.ctrl = spPtr.add(8).readPointer().toString();
      var obj = spPtr.readPointer();
      if (!obj.isNull()) {
        o.vt = obj.readPointer().toString();
        o.strs = scanStrings(obj, size);
        o.hex = hexdump(obj, 0x300);
      }
    } catch (e) { o.err = '' + e; }
    return o;
  }

  // ---- 1) 内容对象构造 ----
  try {
    Interceptor.attach(base.add(0x15f35c0), {
      onEnter: function (args) { this.out = args[0]; },
      onLeave: function (ret) {
        if (!guard('content')) return;
        send({kind:'content_ctor', onLeave: dumpSp(this.out, 'content_out', 0x800)});
      }
    });
    send({kind:'hooked', name:'content_ctor @0x15f35c0'});
  } catch (e) { send({kind:'hookfail', name:'content_ctor', err:''+e}); }

  // ---- 2) 信封构造 ----
  try {
    Interceptor.attach(base.add(0x17040a0), {
      onEnter: function (args) { this.out = args[0]; this.inSp = args[1]; },
      onLeave: function (ret) {
        if (!guard('envelope')) return;
        send({kind:'envelope_ctor',
              out: dumpSp(this.out, 'envelope_out', 0x800),
              inContent: dumpSp(this.inSp, 'envelope_in_content', 0x800)});
      }
    });
    send({kind:'hooked', name:'envelope_ctor @0x17040a0'});
  } catch (e) { send({kind:'hookfail', name:'envelope_ctor', err:''+e}); }

  // ---- 3) 提交 ----
  try {
    Interceptor.attach(base.add(0x160ebe0), {
      onEnter: function (args) {
        if (!guard('commit')) return;
        var rcxs = args[0];
        var rec = {kind:'commit', rcxs: rcxs.toString(), result: args[1].toString(),
                   objs: []};
        try {
          var begin = rcxs.add(8).readPointer();
          var end = rcxs.add(0x10).readPointer();
          var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
          rec.count = cnt;
          for (var i = 0; i < cnt && i < 3; i++) {
            var o = dumpSp(begin.add(i * 16), 'element_' + i, 0x800);
            rec.objs.push(o);
          }
        } catch (e) { rec.err = '' + e; }
        send(rec);
      }
    });
    send({kind:'hooked', name:'commit @0x160ebe0'});
  } catch (e) { send({kind:'hookfail', name:'commit', err:''+e}); }
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


def show(d, indent="    "):
    if not isinstance(d, dict):
        return
    print(f"{indent}{d.get('label')}: sp={d.get('sp')} ptr={d.get('ptr')} ctrl={d.get('ctrl')} vt={d.get('vt')}", flush=True)
    for s in d.get("strs") or []:
        print(f"{indent}  +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s'][:120]!r}", flush=True)
    if d.get("err"):
        print(f"{indent}  err: {d['err']}", flush=True)


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
    print(f"attach pid={pid}，抓取表情构造链，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "sticker_chain.json").write_text(
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
        if k == "content_ctor":
            print("\n=== [CONTENT_CTOR] 内容对象构造 ===", flush=True)
            show(d.get("onLeave", {}))
        elif k == "envelope_ctor":
            print("\n=== [ENVELOPE_CTOR] 信封构造 ===", flush=True)
            show(d.get("inContent", {}), "    输入内容: ")
            show(d.get("out", {}), "    输出信封: ")
        elif k == "commit":
            print(f"\n=== [COMMIT] rcxs={d['rcxs']} 消息数={d.get('count')} ===", flush=True)
            for o in d.get("objs", []):
                show(o)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请发一个收藏表情（表情面板里点一个）", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if len([r for r in records if r.get("kind") == "commit"]) >= 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n共 {len(records)} 条记录，写入 {OUT_DIR / 'sticker_chain.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
