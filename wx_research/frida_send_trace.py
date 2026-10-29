"""追踪真实发送链路：把链上每个候选点全挂上钩子，一次发送确定实际路径。

背景：静态分析得到的工厂 `0x3D67DA0`（唯一调用者 `0x05FAB6A1`）在用户真实发送时
      **未被触发**，但打包点 `0x160EBE0` 被触发了 —— 说明实际路径与静态假设不同。
      全 DLL 有 120+ 处 `0x1B0` 分配，必须用运行时数据而非猜测来决定追哪条。

钩子点（全部为冷路径，不做写操作）：
  0x03D67DA0  内容对象工厂（静态追的那条，验证是否真被调用）
  0x160EBE0  打包（构造 _Ref_count_obj2<vector<shared_ptr>>）
  0x16D5B80  信封工厂 new(0x698)
  0x17040A0  信封初始化
  0x1702FC0  信封子对象构造
  0x16D4450  发送入口（dynamic_cast 后按类型码分派）

用法: python frida_send_trace.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

POINTS = {
    "factory":      0x3D67DA0,   # (rcx=&vec_out, rdx=&shared_ptr<Record>)
    "pack":         0x160EBE0,   # (rcx=&vector<shared_ptr<Content>>, rdx=?)
    "env_factory":  0x16D5B80,   # (rcx=&out_shared_ptr, rdx=&in_shared_ptr)
    "env_init":     0x17040A0,   # (rcx=block, rdx=&in_shared_ptr)
    "sub_ctor":     0x1702FC0,   # (rcx=body, rdx=&in_shared_ptr)
    "send":         0x16D4450,   # (rcx=?, rdx=&out, r8=&in_shared_ptr, r9=?)
}

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var PTS = __PTS__;
  send({kind:'armed', base: base.toString()});

  function h(ptr, n) {
    try { var b = ptr.readByteArray(n); return b ? buf2hex(b) : null; } catch (e) { return null; }
  }
  function buf2hex(ab) {
    var u = new Uint8Array(ab), s = '';
    for (var i = 0; i < u.length; i++) s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
    return s;
  }
  function rd(p) { try { return p.readPointer().toString(); } catch (e) { return null; } }
  function ru32(p) { try { return p.readU32(); } catch (e) { return null; } }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch (e) { return false; } }

  /* 描述一个 shared_ptr（ptr + refctrl），并读出对象的 vtable */
  function shared(sp) {
    try {
      if (!mapped(sp)) return null;
      var p = rd(sp), r = rd(sp.add(Process.pointerSize));
      var vt = (p && p !== '0x0') ? rd(ptr(p)) : null;
      return { ptr: p, refc: r, obj_vt: vt, obj_vt_rva: vt ? (parseInt(vt,16) - parseInt(base.toString(),16)) : null };
    } catch (e) { return null; }
  }

  /* 描述一个 vector<shared_ptr<T>>（&vector） */
  function vecinfo(vp) {
    try {
      if (!mapped(vp)) return null;
      var b = rd(vp.toString()), e = rd(vp.add(8).toString());
      if (b === null || e === null) return null;
      var n = (parseInt(e,16) - parseInt(b,16)) / 16;
      if (!isFinite(n) || n < 0 || n > 64) return { begin:b, end:e, n:null };
      var items = [];
      for (var i = 0; i < n && i < 8; i++) items.push(shared(ptr(b).add(i*16)));
      return { begin: b, end: e, n: n, items: items };
    } catch (e2) { return { err: String(e2) }; }
  }

  var seen = {};
  Object.keys(PTS).forEach(function (name) {
    var addr = base.add(ptr(PTS[name]));
    try {
      Interceptor.attach(addr, {
        onEnter: function (args) {
          var rec = { kind: name, from: this.returnAddress.toString() };
          try {
            if (name === 'factory') {
              rec.vec_out = vecinfo(args[0]);
              rec.in_rec  = shared(args[1]);
            } else if (name === 'pack') {
              rec.vec = vecinfo(args[0]);
              rec.arg2 = args[1].toString();
              rec.arg2_hex = h(args[1], 0x40);
            } else if (name === 'env_factory') {
              rec.out = shared(args[0]);
              rec.in  = shared(args[1]);
            } else if (name === 'env_init') {
              rec.block = args[0].toString();
              rec.block_hex = h(args[0], 0x40);
              rec.in = shared(args[1]);
            } else if (name === 'sub_ctor') {
              rec.body = args[0].toString();
              rec.in = shared(args[1]);
            } else if (name === 'send') {
              rec.rcx = args[0].toString();
              rec.out = shared(args[1]);
              rec.in  = shared(args[2]);
              rec.r9  = args[3].toString();
              if (rec.in && rec.in.obj_vt) {
                rec.in_obj_d8 = (function () {
                  try { return ptr(rec.in.ptr).add(0xd8).readU32(); } catch (e) { return null; }
                })();
              }
            }
          } catch (e) { rec.err = String(e); }
          send(rec);
        }
      });
      seen[name] = 'ok';
    } catch (e) {
      send({ kind: 'hookfail', name: name, err: String(e) });
    }
  });
  send({ kind: 'hooked', which: seen });
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
    src = SCRIPT.replace("__PTS__", json.dumps({k: hex(v) for k, v in POINTS.items()}))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    log = []
    counts = {}

    def flush():
        try:
            (OUT_DIR / "send_trace.json").write_text(
                json.dumps({"counts": counts, "log": log}, ensure_ascii=False, indent=2),
                encoding="utf-8")
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
            print(f"  已挂钩: {d['which']}", flush=True)
            return
        if k == "hookfail":
            print(f"  [挂钩失败] {d['name']}: {d['err']}", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        counts[k] = counts.get(k, 0) + 1
        log.append(d)
        if len(log) <= 60:
            print(f"\n--- [{k}] (第 {counts[k]} 次) caller={d.get('from')}", flush=True)
            for key, val in d.items():
                if key in ("kind", "from"):
                    continue
                if isinstance(val, dict):
                    print(f"    {key}: {json.dumps(val, ensure_ascii=False)[:400]}", flush=True)
                else:
                    print(f"    {key}: {val}", flush=True)
        flush()

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请再发一个收藏表情", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if counts.get("send", 0) >= 1 and counts.get("env_factory", 0) >= 1:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\n命中统计: {counts}", flush=True)
        print(f"写入 {OUT_DIR / 'send_trace.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
