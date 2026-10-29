"""抓取真发送入口 0x16A60D0 的实参，重点判定 R8 包装中 _Ptr 的真实类型。

背景（外部复核指定的唯一待补材料）：
  原生调用点 0x165B8C3：
      0x0165b8b2  lea  rdx, [rbp + 0x260]     ; 参数2
      0x0165b8b9  lea  r8,  [rbp + 0x210]     ; 参数3（shared_ptr 形态）
      0x0165b8c0  mov  rcx, rsi               ; 参数1（ctx）
      0x0165b8c3  call 0x16A60D0
  而 [rbp+0x210] / [rbp+0x218] 在 0x165b8a4 / 0x165b8ab 被写入 rbx / r14。

  需要确认：R8 包装里的 _Ptr 到底是「信封」（vtable 0x82CB8D8）
  还是「请求/任务上下文」（vtable 0x865DEC8），或第三种东西。

本脚本 hook 0x16A60D0 入口，输出：
  1. rcx / rdx / r8 的原始值与返回地址（识别调用者）
  2. R8 指向的 16 字节（shared_ptr 的 _Ptr/_Rep）
  3. R8._Ptr 指向对象的 vtable RVA + 前 0x80 字节
  4. 若 vtable 命中已知值，直接给出类型判断（信封 / 请求上下文 / 其它）
  5. 同时对 0x165B2B0（更上层的通用发送）做一次对照采集

用法: python frida_dump_send_args.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
SEND_ENTRY_RVA = 0x16A60D0
GENERIC_RVA = 0x165B2B0

# 已知 vtable（用于类型判定）
KNOWN_VT = {
    0x82CB8D8: "信封对象体（Envelope）",
    0x82CB848: "信封控制块（_Ref_count_obj2<Envelope>）",
    0x865DEC8: "请求/任务上下文（0x16A77E0 的 R8._Ptr）",
    0x82C74F8: "发送上下文 ctx（会话/服务管理器）",
    0x83DCC28: "内容对象控制块",
    0x8755528: "内容对象体",
}

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var BASEN = parseInt(base.toString(), 16);
  var KNOWN = __KNOWN__;
  send({kind:'armed', base: base.toString()});

  function rvaOf(p) {
    try { var d = parseInt(p.toString(), 16) - BASEN;
          return (d >= 0 && d < 0x10000000) ? d : null; } catch (e) { return null; }
  }
  function rvaStr(p) { var v = rvaOf(p); return v === null ? null : ('0x' + v.toString(16)); }
  function rd(p) { try { return p.readPointer(); } catch (e) { return null; } }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch (e) { return false; } }
  function hexOf(p, n) {
    try { var b = p.readByteArray(n); if (!b) return null;
          var u = new Uint8Array(b), s = '';
          for (var i = 0; i < u.length; i++) s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
          return s; } catch (e) { return null; }
  }
  function u32(p) { try { return p.readU32(); } catch (e) { return null; } }

  function classify(vt_rva) {
    if (vt_rva === null) return null;
    return KNOWN['0x' + vt_rva.toString(16)] || null;
  }

  function descObj(p, depth) {
    if (p === null || p.isNull() || !mapped(p)) return null;
    var o = { ptr: p.toString(), vt_rva: rvaStr(rd(p)), hex: hexOf(p, depth || 0x80) };
    o.vt_kind = classify(rvaOf(rd(p)));
    return o;
  }

  function descShared(sp) {
    if (sp === null || sp.isNull() || !mapped(sp)) return null;
    var ptr = rd(sp), rep = rd(sp.add(8));
    var o = {
      sp_addr: sp.toString(),
      _Ptr: ptr ? ptr.toString() : null,
      _Rep: rep ? rep.toString() : null,
    };
    if (ptr) {
      o.ptr_vt_rva = rvaStr(rd(ptr));
      o.ptr_vt_kind = classify(rvaOf(rd(ptr)));
      o.ptr_hex = hexOf(ptr, 0x80);
    }
    if (rep) {
      o.rep_vt_rva = rvaStr(rd(rep));
    }
    return o;
  }

  /* ---- 真发送入口 ---- */
  Interceptor.attach(base.add(ptr(__SEND__)), {
    onEnter: function (args) {
      var rec = { kind: 'send_entry', caller_rva: rvaStr(this.returnAddress) };
      try {
        rec.rcx = args[0].toString();
        rec.rdx = args[1].toString();
        rec.r8  = args[2].toString();

        /* R8 常为 &shared_ptr：解引用看 _Ptr/_Rep 及其类型 */
        rec.r8_as_shared = descShared(args[2]);
        rec.r8_as_obj    = descObj(args[2], 0x60);

        /* RDX 同理（原生调用点是 &out） */
        rec.rdx_as_shared = descShared(args[1]);
        rec.rdx_as_obj    = descObj(args[1], 0x40);

        /* RCX 是 ctx，验证其 vtable */
        rec.rcx_vt_rva  = rvaStr(rd(args[0]));
        rec.rcx_vt_kind = classify(rvaOf(rd(args[0])));
      } catch (e) { rec.err = String(e); }
      send(rec);
    }
  });

  /* ---- 更上层通用发送（对照）---- */
  Interceptor.attach(base.add(ptr(__GENERIC__)), {
    onEnter: function (args) {
      var rec = { kind: 'generic', caller_rva: rvaStr(this.returnAddress) };
      try {
        rec.rcx_vt_rva = rvaStr(rd(args[0]));
        rec.rcx_vt_kind = classify(rvaOf(rd(args[0])));
        rec.rdx = descObj(args[1], 0x40);
        rec.r8  = descObj(args[2], 0x40);
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
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = (SCRIPT.replace("__SEND__", hex(SEND_ENTRY_RVA))
                .replace("__GENERIC__", hex(GENERIC_RVA))
                .replace("__KNOWN__", json.dumps({hex(k): v for k, v in KNOWN_VT.items()})))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    out = {"send_entry": [], "generic": []}

    def flush():
        try:
            (OUT_DIR / "send_args.json").write_text(
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
            print("  钩子就绪（0x16A60D0 真入口 / 0x165B2B0 通用发送）", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        if k == "send_entry":
            out["send_entry"].append(d)
            flush()
            print("\n" + "=" * 70, flush=True)
            print(f"[send_entry] caller_rva = {d.get('caller_rva')}", flush=True)
            print(f"  rcx = {d.get('rcx')}   类型: {d.get('rcx_vt_kind') or '(未知)'}", flush=True)
            print(f"  rdx = {d.get('rdx')}", flush=True)
            print(f"  r8  = {d.get('r8')}", flush=True)
            sh = d.get("r8_as_shared")
            if sh:
                print("  ── R8 作为 shared_ptr 解引用 ──", flush=True)
                print(f"    _Ptr = {sh.get('_Ptr')}", flush=True)
                print(f"    _Rep = {sh.get('_Rep')}", flush=True)
                print(f"    _Ptr.vtable RVA = {sh.get('ptr_vt_rva')}", flush=True)
                print(f"    ★ 类型判定: {sh.get('ptr_vt_kind') or '**未识别的 vtable**'}", flush=True)
                if sh.get("ptr_hex"):
                    print(f"    _Ptr.hex[:64] = {sh['ptr_hex'][:64]}", flush=True)
            else:
                print("  ── R8 不是可解的 shared_ptr，按对象处理 ──", flush=True)
                o = d.get("r8_as_obj") or {}
                print(f"    vt_rva = {o.get('vt_rva')}  类型: {o.get('vt_kind') or '(未知)'}", flush=True)
                if o.get("hex"):
                    print(f"    hex[:64] = {o['hex'][:64]}", flush=True)
            return
        if k == "generic":
            out["generic"].append(d)
            flush()
            print(f"  [generic] caller_rva={d.get('caller_rva')} "
                  f"rcx类型={d.get('rcx_vt_kind') or '(未知)'}", flush=True)
            return

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请在微信里发一个收藏表情（或任意消息）", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if out["send_entry"]:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\nsend_entry 命中 {len(out['send_entry'])} 次，"
              f"写入 {OUT_DIR / 'send_args.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
