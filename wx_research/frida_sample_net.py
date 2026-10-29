"""系统层采样：hook 网络发送与文件读取，定位微信图片/表情的上传与读取路径。

为什么要下沉到系统层：
    frida 的 Thread.backtrace 在微信里不可靠 —— 上传跑在 fiber/协程里，
    0x64b5d7f 就是 fiber 上下文恢复（mov rsp,[rcx+0x20] / ldmxcsr / jmp rdx），
    协程切栈会让 backtrace 断裂。所以在系统 API 层设观测点更稳。

挂载点：
    ws2_32.WSASend           出网总闸（HTTPS 也走这里）—— 只看大包，识别上传
    winhttp.WinHttpSendRequest  若走 WinHTTP
    kernel32.CreateFileW     读本地文件 —— 过滤图片扩展名
    kernel32.ReadFile        读文件内容
    另加微信内部 3 点（图片XML构造器 / 消息解析器 / 发送提交）

用法:
    python frida_sample_net.py [pid] [seconds]
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

  var MAX = 10;
  var counters = {};

  function btOf(ctx) {
    var out = [];
    try {
      var fr = Thread.backtrace(ctx, Backtracer.ACCURATE);
      for (var i = 0; i < fr.length && i < 10; i++) out.push('0x' + fr[i].sub(base).toString(16));
    } catch (e) { out.push('<err>'); }
    return out;
  }

  function guard(kind) {
    counters[kind] = (counters[kind] || 0);
    if (counters[kind] >= MAX) return false;
    counters[kind]++;
    return true;
  }

  function mod(name) {
    try { return Process.getModuleByName(name); } catch (e) { return null; }
  }

  // ---- WSASend：出网总闸，只看大包 ----
  (function () {
    var m = mod('ws2_32.dll');
    if (!m) return;
    var f = m.findExportByName('WSASend');
    if (!f) return;
    Interceptor.attach(f, {
      onEnter: function (args) {
        try {
          var n = args[2].toInt32();
          var total = 0;
          for (var i = 0; i < n; i++) total += args[1].add(i * 16).readU32();
          if (total < 4096) return;               // 小包是心跳/控制，忽略
          if (!guard('wsasend')) return;
          send({kind:'net', hook:'WSASend', bytes: total,
                bt: btOf(this.context)});
        } catch (e) {
          send({kind:'err', where:'WSASend', msg: '' + e});
        }
      }
    });
    send({kind:'hooked', name:'WSASend @ ws2_32.dll'});
  })();

  // ---- WinHttpSendRequest ----
  (function () {
    var m = mod('winhttp.dll');
    if (!m) { send({kind:'skip', name:'winhttp.dll 未加载'}); return; }
    var f = m.findExportByName('WinHttpSendRequest');
    if (!f) { send({kind:'skip', name:'WinHttpSendRequest 未找到'}); return; }
    Interceptor.attach(f, {
      onEnter: function (args) {
        if (!guard('winhttp')) return;
        var url = null;
        try { url = args[5] ? args[5].readUtf16String() : null; } catch (e) {}
        send({kind:'net', hook:'WinHttpSendRequest',
              hdr_len: args[1].toInt32(), body_len: args[3].toInt32(),
              headers: url, bt: btOf(this.context)});
      }
    });
    send({kind:'hooked', name:'WinHttpSendRequest @ winhttp.dll'});
  })();

  // ---- CreateFileW：读本地图片 ----
  (function () {
    var m = mod('kernel32.dll');
    if (!m) return;
    var f = m.findExportByName('CreateFileW');
    if (!f) return;
    var re = /\.(jpg|jpeg|png|gif|bmp|webp|dat|tif|tiff)$/i;
    Interceptor.attach(f, {
      onEnter: function (args) {
        var p = null;
        try { p = args[0].readUtf16String(); } catch (e) {}
        if (!p || !re.test(p)) return;
        if (!guard('createfile')) return;
        send({kind:'file', hook:'CreateFileW', path: p, bt: btOf(this.context)});
      }
    });
    send({kind:'hooked', name:'CreateFileW @ kernel32.dll'});
  })();

  // ---- 微信内部三点 ----
  var INNER = [['imgxml_xml', 0x21806a0], ['msg_parser', 0xa19440], ['send_commit', 0x160ebe0]];
  INNER.forEach(function (h) {
    try {
      Interceptor.attach(base.add(h[1]), {
        onEnter: function (args) {
          if (!guard(h[0])) return;
          var rec = {kind:'inner', hook: h[0], self: args[0].toString(), bt: btOf(this.context)};
          try {
            var strs = [];
            var p = args[0];
            for (var off = 0; off + 0x20 <= 0x400; off += 8) {
              var len = p.add(off + 0x10).readU64().toNumber();
              var cap = p.add(off + 0x18).readU64().toNumber();
              if (!(len > 0 && len < 1024 && cap >= len && cap <= 0x10000)) continue;
              var sp = (cap <= 0xf) ? p.add(off) : p.add(off).readPointer();
              var s = sp.readUtf8String(len);
              if (s && /^[\x20-\x7e\u4e00-\u9fff]+$/.test(s)) strs.push({off: off, s: s});
            }
            rec.strs = strs;
          } catch (e) {}
          send(rec);
        }
      });
      send({kind:'hooked', name: h[0] + ' @ ' + h[1].toString(16)});
    } catch (e) {
      send({kind:'hookfail', name: h[0], err: '' + e});
    }
  });
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
    print(f"attach pid={pid}，挂载系统层+内部观测点，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []

    def flush():
        try:
            (OUT_DIR / "net_sample.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k in ("hooked", "skip", "armed"):
            print(f"  {k}: {d.get('name') or d.get('base')}", flush=True)
            return
        if k in ("hookfail", "fatal", "err"):
            print(f"  !! {k}: {d}", flush=True)
            return
        records.append(d)
        flush()
        if k == "net":
            print(f"\n=== [NET] {d['hook']}  hdr={d.get('hdr_len')} body={d.get('body_len')} "
                  f"bytes={d.get('bytes')} ===", flush=True)
            if d.get("headers"):
                print(f"    headers: {d['headers'][:200]!r}", flush=True)
        elif k == "file":
            print(f"\n=== [FILE] {d['path']} ===", flush=True)
        elif k == "inner":
            print(f"\n=== [INNER] {d['hook']} this={d['self']} ===", flush=True)
            for s in (d.get("strs") or []):
                print(f"    +{s['off']:#05x} {s['s'][:100]!r}", flush=True)
        print(f"    bt: {d.get('bt')}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.2)
    print("\n已就绪，等待图片/表情操作 ...", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n共 {len(records)} 条记录，写入 {OUT_DIR / 'net_sample.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
