"""在发送提交点 dump 消息对象 —— 直接看表情/图片消息的真实内存结构。

思路：
    0x160ebe0 (CALL3) 是发送链的最终提交，参数 rcxs 是消息容器。
    CALL3 自身反汇编确认容器布局： [rcxs+8] = vector.begin, [rcxs+0x10] = vector.end,
    每个元素 16 字节（shared_ptr: [0]=T*, [8]=控制块，引用计数在 +8）。
    所以提交瞬间可以遍历出每个消息对象指针，dump 其完整首部 + 自动扫描字符串。

这样既能看到表情消息（emojiitem 族）的字段布局，也能对比图片消息体
（已知 vtable 0x80d1128、字段 @0x120..0x230）和文本轻量模型（vtable 0x805E4E8）。

用法:
    python frida_msg_dump.py [pid] [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
COMMIT_RVA = 0x160EBE0

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
    } catch (e) { return '<hexdump err ' + e + '>'; }
  }

  function scanStrings(p, size) {
    var out = [];
    for (var off = 0; off + 0x20 <= size; off += 8) {
      try {
        var len = p.add(off + 0x10).readU64().toNumber();
        var cap = p.add(off + 0x18).readU64().toNumber();
        if (!(len > 0 && len < 2048 && cap >= len && cap <= 0x20000)) continue;
        var sp = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
        var s = sp.readUtf8String(len);
        if (s && /^[\x20-\x7e\u4e00-\u9fff\u3000-\u303f]+$/.test(s))
          out.push({off: off, len: len, s: s});
      } catch (e) {}
    }
    return out;
  }

  var n = 0;
  Interceptor.attach(base.add(0x160ebe0), {
    onEnter: function (args) {
      if (n >= 6) return;
      n++;
      var rcxs = args[0];
      var rec = {kind:'commit', n: n, rcxs: rcxs.toString(), objs: [], vtables: []};
      try {
        var begin = rcxs.add(8).readPointer();
        var end = rcxs.add(0x10).readPointer();
        var diff = end.sub(begin).toInt32();
        var cnt = Math.floor(Math.abs(diff) / 16);
        rec.count = cnt;
        if (cnt > 0 && cnt < 64) {
          for (var i = 0; i < cnt; i++) {
            var elem = begin.add(i * 16);
            var obj = elem.readPointer();
            if (obj.isNull()) continue;
            var o = {idx: i, ptr: obj.toString(),
                     vt: obj.readPointer().toString(),
                     strs: scanStrings(obj, 0x400),
                     hex: hexdump(obj, 0x300)};
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
    print(f"attach pid={pid}，在发送提交点 dump 消息对象，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "msg_dump.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

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
        print(f"\n########## 提交 #{d.get('n')}  rcxs={d.get('rcxs')}  消息数={d.get('count')} ##########", flush=True)
        if d.get("err"):
            print(f"  遍历失败: {d['err']}", flush=True)
        for o in d.get("objs", []):
            print(f"\n  --- 消息[{o['idx']}] ptr={o['ptr']} vtable={o['vt']} ---", flush=True)
            for s in o.get("strs", []):
                print(f"      +{s['off']:#05x} len={s['len']:<5} {s['s'][:110]!r}", flush=True)
            print("      hex:", flush=True)
            for line in o.get("hex", "").splitlines():
                print("        " + line, flush=True)

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
        print(f"\n共 {len(records)} 次提交，写入 {OUT_DIR / 'msg_dump.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
