"""精确采集内容对象：hook operator new 并按分配大小过滤。

为什么换这个方法：
    之前用「hook 提交点 → 拿 shared_ptr → 扫字符串」的方式，得到的是**猜测的字段偏移**，
    而且我手工做 RVA 换算时出过 0x120000 的错误，把两个不同类混成一个。
    更可靠的锚点是「分配点」——对象刚分配出来时地址和大小都是确定的，不依赖任何换算。

本脚本：
  1. hook operator new (0x64a7d1c)，当申请大小 == 0x1B0 时记录返回地址（内容对象）
     —— 0x1B0 是 0x83dcc28 那个类的分配大小（见构造序列 mov ecx, 0x1b0）
  2. hook 该对象被填充后的提交点 (0x160EBE0)，把对象完整 dump 出来（含 raw 头 0x10）
  3. 所有地址都原样上报，**不在 frida 里做 RVA 换算**，由 Python 端用 base 统一处理

用法:
    python frida_sticker_precise.py [pid] [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
CONTENT_SIZE = 0x1B0

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

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

  /* 扫描一个对象里的 MSVC std::string（32 字节：buf@0 len@0x10 cap@0x18） */
  function scanStrings(p, size) {
    var out = [];
    for (var off = 0; off + 0x20 <= size; off += 8) {
      try {
        var len = p.add(off + 0x10).readU64().toNumber();
        var cap = p.add(off + 0x18).readU64().toNumber();
        if (!(len > 0 && len < 8192 && cap >= len && cap <= 0x40000)) continue;
        var sp = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
        var s = sp.readUtf8String(len);
        if (s && /^[\x20-\x7e\u4e00-\u9fff\u3000-\u303f]+$/.test(s))
          out.push({off: off, len: len, cap: cap, s: s});
      } catch (e) {}
    }
    return out;
  }

  var allocs = [];          // 本次运行中按 0x1B0 分配的块
  var MAXALLOC = 40;

  // ---- 1) operator new 过滤 ----
  try {
    Interceptor.attach(base.add(0x64a7d1c), {
      onEnter: function (args) { this.size = args[0].toInt32(); },
      onLeave: function (ret) {
        if (this.size !== 0x1B0) return;
        if (allocs.length >= MAXALLOC) return;
        var obj = ret;
        allocs.push(obj);
        send({kind:'alloc_1b0', block: obj.toString(),
              block_rva_minus: obj.sub(base).toString(),
              obj_body: obj.add(0x10).toString(),
              vt_at_block: (function(){ try { return obj.readPointer().toString(); } catch(e){ return null; } })(),
              vt_at_body:  (function(){ try { return obj.add(0x10).readPointer().toString(); } catch(e){ return null; } })(),
              strs: scanStrings(obj, 0x1B0),
              hex: hexdump(obj, 0x1B0)});
      }
    });
    send({kind:'hooked', name:'operator_new @0x64a7d1c (filter 0x1B0)'});
  } catch (e) { send({kind:'hookfail', name:'operator_new', err:''+e}); }

  // ---- 2) 提交点：确认哪个对象最终入队 ----
  try {
    Interceptor.attach(base.add(0x160ebe0), {
      onEnter: function (args) {
        var rcxs = args[0];
        var rec = {kind:'commit', rcxs: rcxs.toString(), result: args[1].toString(), objs: []};
        try {
          var begin = rcxs.add(8).readPointer();
          var end = rcxs.add(0x10).readPointer();
          var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
          rec.count = cnt;
          for (var i = 0; i < cnt && i < 3; i++) {
            var elem = begin.add(i * 16);
            var env = elem.readPointer();
            var o = {idx: i, env_ptr: env.toString(),
                     env_rva: env.sub(base).toString(),
                     env_vt: (function(){ try { return env.readPointer().toString(); } catch(e){ return null; } })(),
                     env_strs: scanStrings(env, 0x800)};
            // 跟随 +0x668 的内容子对象（shared_ptr）
            try {
              var contentSp = env.add(0x668);
              var cptr = contentSp.readPointer();
              o.content_ptr = cptr.toString();
              o.content_rva = cptr.sub(base).toString();
              o.content_ctrl = contentSp.add(8).readPointer().toString();
              o.content_vt = cptr.readPointer().toString();
              o.content_vt_rva = cptr.readPointer().sub(base).toString();
              o.content_strs = scanStrings(cptr, 0x200);
              o.content_hex = hexdump(cptr, 0x180);
              o.content_is_alloc_1b0 = allocs.some(function (b) { return b.equals(cptr.sub(0x10)); });
            } catch (e) { o.content_err = '' + e; }
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


BASE = {"v": None}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    pid = pick_pid(sys.argv[1] if len(sys.argv) > 1 else None)
    if not pid:
        print("找不到主进程")
        return 1
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，精确采集内容对象，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "sticker_precise.json").write_text(
                json.dumps({"base": BASE["v"], "records": records},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def to_rva(addr_str):
        """在 Python 端统一换算，避免手工算错"""
        try:
            b = BASE["v"]
            if not b:
                return None
            return hex(int(addr_str, 16) - int(b, 16))
        except Exception:
            return None

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:200], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            BASE["v"] = d["base"]
            print(f"  base = {d['base']}", flush=True)
            return
        if k in ("hooked", "hookfail", "fatal"):
            print(f"  {k}: {d.get('name') or d.get('err')}", flush=True)
            return
        records.append(d)
        flush()
        if k == "alloc_1b0":
            blk = d["block"]
            print(f"\n=== [ALLOC 0x1B0] block={blk} RVA={to_rva(blk)} ===", flush=True)
            print(f"    block 处的指针(RVA {to_rva(d.get('vt_at_block'))})  body={d['obj_body']} RVA={to_rva(d['obj_body'])}", flush=True)
            print(f"    它内部 +0x10 处指针(RVA {to_rva(d.get('vt_at_body'))})", flush=True)
            for s in d.get("strs", []):
                print(f"    +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s'][:100]!r}", flush=True)
        elif k == "commit":
            print(f"\n=== [COMMIT] 消息数={d.get('count')} ===", flush=True)
            for o in d.get("objs", []):
                print(f"  信封 ptr={o.get('env_ptr')} RVA={to_rva(o.get('env_ptr'))} vt_rva={to_rva(o.get('env_vt'))}", flush=True)
                for s in o.get("env_strs", []):
                    print(f"    信封 +{s['off']:#05x} {s['s'][:90]!r}", flush=True)
                print(f"  内容 ptr={o.get('content_ptr')} RVA={to_rva(o.get('content_ptr'))} "
                      f"vt_rva={o.get('content_vt_rva')} ctrl={o.get('content_ctrl')}", flush=True)
                print(f"  内容是否是 0x1B0 分配出来的块(+0x10)? {o.get('content_is_alloc_1b0')}", flush=True)
                for s in o.get("content_strs", []):
                    print(f"    内容 +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s'][:100]!r}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请发一个收藏表情", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if any(r.get("kind") == "commit" for r in records):
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n共 {len(records)} 条记录，写入 {OUT_DIR / 'sticker_precise.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
