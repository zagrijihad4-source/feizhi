"""捕获 send_sticker 阶段3（包信封）的异常现场。

用法:
    python frida_sticker_diag.py [pid]
然后在另一个终端触发一次 type=3（或直接用本脚本内嵌触发）。

它会：
  1. 安装全局异常处理器，记录异常类型/地址/关键寄存器
  2. hook 0x17040a0（信封构造）入口，dump 两个参数及其解引用结果
  3. hook 0x1702fc0（包信封核心）入口，dump 参数与引用计数
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

  Process.setExceptionHandler(function (d) {
    var ctx = d.context || {};
    var o = {kind:'exception', etype: d.type, address: d.address ? d.address.toString() : null};
    ['pc','rip','rcx','rdx','r8','r9','rax','rbx','rsi','rdi'].forEach(function (k) {
      try { if (ctx[k]) o[k] = ctx[k].toString(); } catch (e) {}
    });
    send(o);
    return false;   // 交给程序自身 SEH 处理
  });

  function snap(p, label, o) {
    try { o[label + '_ptr'] = p.readPointer().toString(); } catch (e) { o[label + '_err'] = '' + e; }
  }

  try {
    Interceptor.attach(base.add(0x17040a0), {
      onEnter: function (args) {
        var o = {kind:'env_ctor_enter', a1: args[0].toString(), a2: args[1].toString()};
        snap(args[0], 'a1_0', o);
        snap(args[1], 'a2_0', o);
        try {
          var ctrl = args[1].add(8).readPointer();
          o.a2_8 = ctrl.toString();
          if (!ctrl.isNull()) o.a2_8_refcnt = ctrl.add(8).readU32();
        } catch (e) { o.a2_8_err = '' + e; }
        try { o.a1_head = args[0].readByteArray(16) ? 'readable' : 'no'; } catch (e) { o.a1_head = '' + e; }
        send(o);
      },
      onLeave: function (ret) {
        send({kind:'env_ctor_leave', ret: ret ? ret.toString() : null});
      }
    });
    send({kind:'hooked', name:'env_ctor @0x17040a0'});
  } catch (e) { send({kind:'hookfail', name:'env_ctor', err:''+e}); }

  // ---- 在 0x17040a0 内部沿途设轨迹点，精确定位崩在哪一句 ----
  var TRACE = [
    [0x17040c1, 'write_refcnt_rcx_plus8'],
    [0x17040cc, 'write_vtable_rcx0'],
    [0x17040da, 'load_content_ctrl'],
    [0x17040e3, 'lock_inc_ctrl'],
    [0x170411e, 'store_local_sp_a'],
    [0x170412a, 'call_pack_core']
  ];
  TRACE.forEach(function (t) {
    try {
      Interceptor.attach(base.add(t[0]), {
        onEnter: function () { send({kind:'trace', at: t[0].toString(16), name: t[1]}); }
      });
      send({kind:'hooked', name:'trace ' + t[1]});
    } catch (e) { send({kind:'hookfail', name:'trace ' + t[1], err:''+e}); }
  });

  try {
    Interceptor.attach(base.add(0x1702fc0), {
      onEnter: function (args) {
        var o = {kind:'pack_core_enter', a1: args[0].toString(), a2: args[1].toString()};
        snap(args[1], 'a2_0', o);
        try {
          var ctrl = args[1].add(8).readPointer();
          o.a2_8 = ctrl.toString();
          if (!ctrl.isNull()) o.a2_8_refcnt = ctrl.add(8).readU32();
        } catch (e) { o.a2_8_err = '' + e; }
        send(o);
      }
    });
    send({kind:'hooked', name:'pack_core @0x1702fc0'});
  } catch (e) { send({kind:'hookfail', name:'pack_core', err:''+e}); }
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
        print("找不到主进程")
        return 1
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    print(f"attach pid={pid}")
    session = frida.attach(pid)

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:200], flush=True)
            return
        d = msg["payload"]
        print(f"  [{d.get('kind')}] {json.dumps(d, ensure_ascii=False)}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)

    # 自动触发一次 type=3
    base = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge")
    seq = str(int(time.time() * 1000))
    (base / "outbox" / "next.txt").write_text(
        seq + "\t3\t" + "<WXID_FRIEND_A>" + "\t" + "0", encoding="utf-8")
    print(f"\n已触发 type=3 (seq={seq})，等待异常/返回 ...", flush=True)

    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
