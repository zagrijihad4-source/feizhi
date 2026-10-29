"""捕获通用发送函数 0x165B2B0 的上下文对象，并判定其是否持久。

背景（TASK_LOG 第十二/十三节）：
  0x16D4450 只返回信封，不发送；
  0x34F01F0 只是比较 [ctx+8] 与 env 并记日志；
  再往上是 0x16A60D0 → 0x165B2B0（通用消息发送，4 个调用者）。

  0x165B2B0 入口：
      0x0165b2e0  mov  rsi, rcx        ; 上下文对象
      0x0165b2f4  mov  rax, [rsi+0xb78]
  说明 rcx 是一个带 +0xb78 字段的对象，很可能是持久会话管理器。

本脚本：
  1. 抓 0x165B2B0 的 rcx（上下文）指针对与 vtable RVA
  2. 抓调用者 RVA
  3. 发送后由外部脚本用 ReadProcessMemory 复读同一地址，判断对象是否仍存活
     —— 若仍存活（vtable 不变），即可复用它直接驱动发送

用法: python frida_sendctx_capture.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
GENERIC_SEND_RVA = 0x165B2B0
SEND_WRAPPER_RVA = 0x16A60D0

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var BASEN = parseInt(base.toString(), 16);
  send({kind:'armed', base: base.toString()});

  function rvaOf(p) {
    try { var d = parseInt(p.toString(),16) - BASEN;
          return (d >= 0 && d < 0x10000000) ? ('0x' + d.toString(16)) : null; } catch(e){ return null; }
  }
  function rd(p) { try { return p.readPointer(); } catch(e) { return null; } }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch(e) { return false; } }
  function hexOf(p,n) {
    try { var b = p.readByteArray(n); if(!b) return null;
          var u = new Uint8Array(b), s='';
          for (var i=0;i<u.length;i++) s += (u[i]<16?'0':'')+u[i].toString(16);
          return s; } catch(e){ return null; }
  }
  function u32(p) { try { return p.readU32(); } catch(e) { return null; } }
  function u64(p) { try { return p.readU64().toString(); } catch(e) { return null; } }

  function desc(p) {
    if (p === null || p.isNull()) return null;
    var o = { ptr: p.toString(), vt: null, vt_rva: null, hex: null };
    if (mapped(p)) {
      var vt = rd(p);
      o.vt = vt ? vt.toString() : null;
      o.vt_rva = vt ? rvaOf(vt) : null;
      o.hex = hexOf(p, 0x40);
    }
    return o;
  }

  /* 通用发送：rcx = 上下文 */
  Interceptor.attach(base.add(ptr(__GENERIC__)), {
    onEnter: function (args) {
      var rec = { kind: 'generic_send', caller_rva: rvaOf(this.returnAddress) };
      try {
        var ctx = args[0];
        rec.ctx = desc(ctx);
        if (ctx !== null && !ctx.isNull() && mapped(ctx)) {
          rec.ctx_0xb78 = u64(ctx.add(0xb78));
          rec.ctx_0xb78_desc = desc(rd(ctx.add(0xb78)));
        }
        rec.arg2 = desc(args[1]);
      } catch (e) { rec.err = String(e); }
      send(rec);
    }
  });

  /* 上一层包装：rcx = 上下文, rdx = &out, r8 = &ctx_sp */
  Interceptor.attach(base.add(ptr(__WRAPPER__)), {
    onEnter: function (args) {
      send({ kind: 'wrapper', caller_rva: rvaOf(this.returnAddress),
             rcx: args[0].toString(), r8_ptr: desc(args[2]) });
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
    src = (SCRIPT.replace("__GENERIC__", hex(GENERIC_SEND_RVA))
                .replace("__WRAPPER__", hex(SEND_WRAPPER_RVA)))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    out = {"generic": [], "wrapper": []}
    ctx_seen: dict = {}

    def flush():
        try:
            (OUT_DIR / "sendctx_capture.json").write_text(
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
            print("  钩子就绪（0x165B2B0 通用发送 / 0x16A60D0 包装）", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        if k == "generic_send":
            out["generic"].append(d)
            flush()
            c = d.get("ctx") or {}
            print(f"\n=== [generic_send] caller_rva={d.get('caller_rva')} ===", flush=True)
            print(f"  ctx = {c.get('ptr')}  vt_rva={c.get('vt_rva')}", flush=True)
            print(f"  ctx+0xb78 = {d.get('ctx_0xb78')}  "
                  f"desc={json.dumps(d.get('ctx_0xb78_desc'), ensure_ascii=False)[:160]}", flush=True)
            if c.get("ptr"):
                ctx_seen[c["ptr"]] = c.get("vt_rva")
            return
        if k == "wrapper":
            out["wrapper"].append(d)
            flush()
            gp = d.get("r8_ptr") or {}
            print(f"  [wrapper] caller_rva={d.get('caller_rva')} rcx={d.get('rcx')} "
                  f"r8_ptr={gp.get('ptr')} vt_rva={gp.get('vt_rva')}", flush=True)
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
            if out["generic"]:
                time.sleep(3.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\ngeneric_send 命中 {len(out['generic'])} 次", flush=True)
        print(f"上下文对象候选: {json.dumps(ctx_seen, ensure_ascii=False)}", flush=True)
        print(f"写入 {OUT_DIR / 'sendctx_capture.json'}", flush=True)
        if ctx_seen:
            print("\n下一步：用 ReadProcessMemory 复读这些地址，判断是否仍存活", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
