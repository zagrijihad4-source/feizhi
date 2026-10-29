"""最后一击：在发送入口 dump 信封全文，并追踪信封内的内容指针。

已知（运行时 + 静态双证）：
  0x16D4450(rcx=?, rdx=&out, r8=&shared_ptr<Envelope>, r9=?)
  Envelope.body = vtable 0x82CB8D8，body+0xd8 = 0x2F（收藏表情类型码）
  信封总大小 0x698，由 0x1AFE710 或 0x16D5B80 分配，输出 {ptr=block+0x10, _Rep=block}

本脚本产出：
  1. send 入口处信封的完整 0x688 字节（body 起）—— 这是"要发出去的东西"的全貌
  2. 信封内每个"疑似内容指针"字段实际指向什么（是否 mapped、对象 vtable、前 0x80 字节）
  3. 信封工厂 0x1AFE710 的调用者 —— 确定 7 个场景里是哪一个
  4. 发送主函数 0x16A77E0 的调用者

用法: python frida_env_dump.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

SEND_RVA = 0x16D4450
ENVFAC_RVA = 0x1AFE710
SENDMAIN_RVA = 0x16A77E0
PACK_RVA = 0x160EBE0

# 信封内值得追踪的指针字段（相对 body）
CAND_OFFS = [0x0a0, 0x0a8, 0x0b0, 0x0b8, 0x0d0, 0x0d8,
             0x100, 0x108, 0x110, 0x118, 0x120, 0x128,
             0x160, 0x168, 0x170, 0x178,
             0x5f0, 0x5f8, 0x600, 0x608, 0x610, 0x618,
             0x620, 0x628, 0x630, 0x638, 0x640, 0x648,
             0x650, 0x658, 0x660, 0x668, 0x670, 0x678, 0x680]

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var BASEN = parseInt(base.toString(), 16);
  var OFF = __OFFS__;
  send({kind:'armed', base: base.toString()});

  function h(p, n) {
    try { var b = p.readByteArray(n); return b ? buf2hex(b) : null; } catch (e) { return null; }
  }
  function buf2hex(ab) {
    var u = new Uint8Array(ab), s = '';
    for (var i = 0; i < u.length; i++) s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
    return s;
  }
  function rd(p) { try { return p.readPointer().toString(); } catch (e) { return null; } }
  function rva(p) {
    var v = parseInt(p, 16);
    if (!isFinite(v)) return null;
    var d = v - BASEN;
    return (d >= 0 && d < 0x10000000) ? d : null;
  }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch (e) { return false; } }
  function tryStr(p) {
    /* MSVC string：buf@0, len@0x10, cap@0x18 */
    try {
      var cap = p.add(0x18).readU64().toNumber();
      var len = p.add(0x10).readU64().toNumber();
      if (len <= 0 || len > 0x4000) return null;
      var data = (cap <= 0xf) ? p.readByteArray(Math.min(len, 200))
                              : p.readPointer().readByteArray(Math.min(len, 200));
      if (!data) return null;
      var u = new Uint8Array(data), s = '';
      for (var i = 0; i < u.length; i++) {
        var c = u[i];
        s += (c >= 32 && c < 127) ? String.fromCharCode(c) : '.';
      }
      return s;
    } catch (e) { return null; }
  }

  /* 深挖一个疑似指针：判断它是什么 */
  function probe(p) {
    if (!p || p.isNull() || !mapped(p)) return null;
    var o = { ptr: p.toString(), vt: rd(p), vt_rva: null };
    if (o.vt) o.vt_rva = rva(o.vt);
    o.hex = h(p, 0x60);
    var s = tryStr(p);
    if (s) o.msvc_string = s;
    return o;
  }

  var dumps = [];

  /* ---- send 入口：dump 信封全文 ---- */
  Interceptor.attach(base.add(ptr(__SEND__)), {
    onEnter: function (args) {
      var rec = { kind: 'send', caller: this.returnAddress.toString(),
                  caller_rva: rva(this.returnAddress.toString()) };
      try {
        var sp = args[2];
        var env = sp.readPointer();
        var refc = sp.add(8).readPointer();
        rec.env = env.toString();
        rec.env_refc = refc.toString();
        rec.env_vt = rd(env);
        rec.env_vt_rva = rva(rec.env_vt);
        rec.env_d8 = env.add(0xd8).readU32();
        rec.cands = {};
        OFF.forEach(function (off) {
          var pr = probe(env.add(off));
          if (pr) rec.cands['0x' + off.toString(16)] = pr;
        });
        dumps.push(rec);
        send(rec);
        /* 信封全文单独发，避免超大单条消息 */
        send({ kind: 'env_body', env: env.toString(), hex: h(env, 0x688) });
      } catch (e) {
        rec.err = String(e);
        send(rec);
      }
    }
  });

  /* ---- 信封工厂：记录调用者 ---- */
  Interceptor.attach(base.add(ptr(__ENVFAC__)), {
    onEnter: function (args) {
      send({ kind: 'env_factory', caller: this.returnAddress.toString(),
             caller_rva: rva(this.returnAddress.toString()) });
    }
  });

  /* ---- 发送主函数：记录调用者 ---- */
  Interceptor.attach(base.add(ptr(__SENDMAIN__)), {
    onEnter: function (args) {
      send({ kind: 'send_main', caller: this.returnAddress.toString(),
             caller_rva: rva(this.returnAddress.toString()) });
    }
  });

  /* ---- 打包点：dump rcx 指向的 vector<shared_ptr> ---- */
  Interceptor.attach(base.add(ptr(__PACK__)), {
    onEnter: function (args) {
      var rec = { kind: 'pack', caller: this.returnAddress.toString(),
                  caller_rva: rva(this.returnAddress.toString()) };
      try {
        var vp = args[0];
        rec.vec_ptr = vp.toString();
        rec.vec_hex = h(vp, 0x20);
        var b = rd(vp), e = rd(vp.add(8));
        rec.begin = b; rec.end = e;
        if (b && e) {
          var n = (parseInt(e,16) - parseInt(b,16)) / 16;
          rec.n = (isFinite(n) && n >= 0 && n <= 32) ? n : null;
          rec.items = [];
          for (var i = 0; i < (rec.n || 0); i++) {
            var sp = ptr(b).add(i*16);
            var p = rd(sp), r = rd(sp.add(8));
            var vt = p ? rd(ptr(p)) : null;
            rec.items.push({ ptr: p, refc: r, vt: vt, vt_rva: vt ? rva(vt) : null,
                             hex: p ? h(ptr(p), 0x120) : null });
          }
        }
      } catch (e2) { rec.err = String(e2); }
      send(rec);
    }
  });

  send({ kind: 'hooked' });
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

    src = (SCRIPT
           .replace("__SEND__", hex(SEND_RVA))
           .replace("__ENVFAC__", hex(ENVFAC_RVA))
           .replace("__SENDMAIN__", hex(SENDMAIN_RVA))
           .replace("__PACK__", hex(PACK_RVA))
           .replace("__OFFS__", json.dumps(CAND_OFFS)))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    out = {"sends": [], "env_bodies": [], "events": []}

    def flush():
        try:
            (OUT_DIR / "env_dump.json").write_text(
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
            print("  全部钩子就绪（send / env_factory / send_main / pack）", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        if k == "env_body":
            out["env_bodies"].append(d)
            flush()
            print(f"\n=== 信封全文已抓 ({d['env']}, {len(d.get('hex') or '')//2} 字节) ===", flush=True)
            return
        if k == "send":
            out["sends"].append(d)
            flush()
            print(f"\n=== [send] caller_rva={d.get('caller_rva')} env={d.get('env')} "
                  f"vt_rva={d.get('env_vt_rva')} d8={d.get('env_d8')} ===", flush=True)
            for off, pr in (d.get("cands") or {}).items():
                line = f"    body{off}: ptr={pr['ptr']} vt_rva={pr.get('vt_rva')}"
                if pr.get("msvc_string"):
                    line += f"  str={pr['msvc_string'][:100]!r}"
                print(line, flush=True)
            return
        out["events"].append(d)
        flush()
        print(f"  [{k}] caller_rva={d.get('caller_rva')}", flush=True)
        if k == "pack":
            print(f"      vec={d.get('vec_ptr')} n={d.get('n')} "
                  f"hex={(d.get('vec_hex') or '')[:80]}", flush=True)
            for i, it in enumerate(d.get("items") or []):
                print(f"      item[{i}] ptr={it['ptr']} vt_rva={it.get('vt_rva')}", flush=True)
                if it.get("hex"):
                    print(f"          hex[:96]={it['hex'][:96]}", flush=True)
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
            if out["sends"] and out["env_bodies"]:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\nsend 命中 {len(out['sends'])} 次，事件 {len(out['events'])} 条，"
              f"写入 {OUT_DIR / 'env_dump.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
