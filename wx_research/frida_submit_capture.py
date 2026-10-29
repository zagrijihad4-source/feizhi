"""捕获真正的发送提交函数 0x34F01F0 的调用参数。

背景（见 TASK_LOG 第十二节）：
  0x16D4450 只是「校验并原样返回信封」，并非提交。真正的提交在
  0x16A77E0 内部的 0x16A7EB0 处：
      0x016a7ea6  lea  rdx, [rbp+0x130]   ; &shared_ptr<Envelope>
      0x016a7ead  mov  rcx, rdi           ; 上下文对象
      0x016a7eb0  call 0x34F01F0

  `0x34F01F0` 内部立刻读 [rcx+0x18] 再读 [+0x104]，说明 rcx 是个必需对象，
  传 NULL 必崩。

本脚本在真实发送时抓：
  1. rcx（上下文对象）指针 + 前 0x60 字节 + 其 vtable RVA
  2. [rcx+0x18] 指向的对象 + 其 vtable RVA
  3. rdx（&shared_ptr<Envelope>）指向的信封信息
  4. 调用者 RVA

目标：判断这个上下文对象是否为持久单例 —— 若是，即可直接
      调用 0x34F01F0(context, &env_sp) 完成程序化发送。

用法: python frida_submit_capture.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
SUBMIT_RVA = 0x34F01F0
SENDMAIN_RVA = 0x16A77E0

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var BASEN = parseInt(base.toString(), 16);
  send({kind:'armed', base: base.toString()});

  function rvaOf(p) {
    try {
      var d = parseInt(p.toString(), 16) - BASEN;
      return (d >= 0 && d < 0x10000000) ? ('0x' + d.toString(16)) : null;
    } catch (e) { return null; }
  }
  function rd(p) { try { return p.readPointer(); } catch (e) { return null; } }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch (e) { return false; } }
  function hexOf(p, n) {
    try { var b = p.readByteArray(n); if (!b) return null;
          var u = new Uint8Array(b), s = '';
          for (var i = 0; i < u.length; i++) s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
          return s; } catch (e) { return null; }
  }
  function u32(p) { try { return p.readU32(); } catch (e) { return null; } }

  function desc(p) {
    if (p === null || p.isNull()) return null;
    var o = { ptr: p.toString(), vt: null, vt_rva: null, hex: null };
    if (mapped(p)) {
      var vt = rd(p);
      o.vt = vt ? vt.toString() : null;
      o.vt_rva = vt ? rvaOf(vt) : null;
      o.hex = hexOf(p, 0x60);
    }
    return o;
  }

  Interceptor.attach(base.add(ptr(__SUBMIT__)), {
    onEnter: function (args) {
      var rec = { kind: 'submit', caller_rva: rvaOf(this.returnAddress) };
      try {
        var ctx = args[0];       // rcx
        var sp  = args[1];       // rdx = &shared_ptr<Envelope>
        rec.ctx = desc(ctx);
        if (ctx !== null && !ctx.isNull() && mapped(ctx)) {
          var sub = rd(ctx.add(0x18));
          rec.ctx_0x18 = desc(sub);
          if (sub && mapped(sub)) {
            rec.ctx_0x18_0x104 = u32(sub.add(0x104));
          }
        }
        if (sp !== null && mapped(sp)) {
          var env = rd(sp);
          rec.env = desc(env);
          rec.env_type = env && mapped(env) ? u32(env.add(0xd8)) : null;
        }
      } catch (e) { rec.err = String(e); }
      send(rec);
    }
  });

  Interceptor.attach(base.add(ptr(__SENDMAIN__)), {
    onEnter: function (args) {
      var rec = { kind: 'sendmain', caller_rva: rvaOf(this.returnAddress) };
      try {
        rec.rcx = desc(args[0]);
        rec.r8 = desc(args[2]);   // &shared_ptr<Context>
        if (args[2] && mapped(args[2])) {
          rec.r8_ptr = desc(rd(args[2]));
        }
      } catch (e) { rec.err = String(e); }
      send(rec);
    }
  });

  send({kind:'hooked'});
}
"""


def pick_pid(explicit):
    if explicit:
        return int(explicit)
    import subprocess
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process Weixin -ErrorAction SilentlyContinue | "
         "Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -First 1).Id"],
        capture_output=True, text=True)
    try:
        return int(out.stdout.strip())
    except Exception:
        return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    pid = pick_pid(sys.argv[1] if len(sys.argv) > 1 else None)
    if not pid:
        print("找不到微信主进程")
        return 1
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = (SCRIPT.replace("__SUBMIT__", hex(SUBMIT_RVA))
                .replace("__SENDMAIN__", hex(SENDMAIN_RVA)))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    out = {"submits": [], "sendmains": []}

    def flush():
        try:
            (OUT_DIR / "submit_capture.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def on_message(msg, data=None):
        if msg.get("type") == "error":
            print("  [script error]", msg.get("description"), flush=True)
            return
        if msg.get("type") != "send":
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            print(f"  base={d['base']}", flush=True)
            return
        if k == "hooked":
            print("  钩子就绪（0x34F01F0 提交点 / 0x16A77E0 发送主函数）", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        if k == "submit":
            out["submits"].append(d)
            flush()
            print("\n=== [submit] 0x34F01F0 被调用 ===", flush=True)
            c = d.get("ctx") or {}
            print(f"  ctx        = {c.get('ptr')}  vt_rva={c.get('vt_rva')}", flush=True)
            s = d.get("ctx_0x18") or {}
            print(f"  ctx+0x18   = {s.get('ptr')}  vt_rva={s.get('vt_rva')}  "
                  f"[+0x104]={d.get('ctx_0x18_0x104')}", flush=True)
            e = d.get("env") or {}
            print(f"  env        = {e.get('ptr')}  vt_rva={e.get('vt_rva')}  "
                  f"类型码={d.get('env_type')}", flush=True)
            if c.get("hex"):
                print(f"  ctx hex[:96] = {c['hex'][:96]}", flush=True)
            return
        if k == "sendmain":
            out["sendmains"].append(d)
            flush()
            r = d.get("rcx") or {}
            g = d.get("r8") or {}
            gp = d.get("r8_ptr") or {}
            print(f"  [sendmain] rcx={r.get('ptr')} vt_rva={r.get('vt_rva')}  "
                  f"r8={g.get('ptr')} -> ptr={gp.get('ptr')} vt_rva={gp.get('vt_rva')}", flush=True)
            return

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请再发一个收藏表情", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if out["submits"]:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\nsubmit 命中 {len(out['submits'])} 次，写入 {OUT_DIR / 'submit_capture.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
