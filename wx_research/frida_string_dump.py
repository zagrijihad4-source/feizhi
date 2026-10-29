"""最终采样：dump 内容对象里每个 std::string 的实际文本。

已知内容对象布局（静态 + 运行时双证，见 TASK_LOG 第九节）：
  block+0x00  控制块 vtable (0x83DCC28)
  block+0x08  _Uses | _Weaks<<32
  block+0x10  对象体 vtable (0x8755528)  ← 对象体起点
  block+0x20  第1个 std::string（buf/len@+0x10/cap@+0x18，stride 0x20）md5
  ...
  block+0x660 阶段：信封 +0x660 / +0x668 是一对 shared_ptr，指向内容对象

本脚本在发送入口 (0x16D4450) 处：
  1. 取信封 body = [r8]
  2. 取内容对象 shared_ptr = {body+0x660 (_Ptr), body+0x668 (_Rep)}
  3. 验证 _Rep == _Ptr - 0x10 且 [_Rep] == base+0x83DCC28
  4. 读出该对象全部 12 个 std::string 的实际文本（含堆缓冲）
  5. 同时记录信封自身的 string（wxid / UUID）

用法: python frida_string_dump.py <pid> <seconds>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
SEND_RVA = 0x16D4450
CONTENT_VT_RVA = 0x83DCC28
BODY_VT_RVA = 0x8755528

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

  function rd(p) { try { return p.readPointer(); } catch (e) { return null; } }
  function mapped(p) { try { return Process.findRangeByAddress(p) !== null; } catch (e) { return false; } }
  function hexOf(p, n) {
    try { var b = p.readByteArray(n); return b ? buf2hex(b) : null; } catch (e) { return null; }
  }
  function buf2hex(ab) {
    var u = new Uint8Array(ab), s = '';
    for (var i = 0; i < u.length; i++) s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
    return s;
  }
  function rvaOf(p) {
    try {
      var d = parseInt(p.toString(), 16) - parseInt(base.toString(), 16);
      return (d >= 0 && d < 0x10000000) ? ('0x' + d.toString(16)) : null;
    } catch (e) { return null; }
  }
  function u64(p) { try { return p.readU64().toNumber(); } catch (e) { return null; } }
  function u32(p) { try { return p.readU32(); } catch (e) { return null; } }

  /* 读一个 MSVC std::string：buf@+0, len@+0x10, cap@+0x18 */
  function readStr(sp) {
    try {
      var cap = u64(sp.add(0x18));
      var ln = u64(sp.add(0x10));
      if (cap === null || ln === null) return { err: 'unreadable' };
      var out = { len: ln, cap: cap, sso: cap <= 0xf, buf: null, text: null, hex: null };
      if (ln === 0) { out.text = ''; return out; }
      if (ln > 0x8000) return { err: 'len too big', len: ln, cap: cap };
      var bp;
      if (cap <= 0xf) { bp = sp; }
      else { bp = rd(sp); if (bp === null || !mapped(bp)) return { err: 'bad buf', len: ln, cap: cap }; }
      out.buf = bp.toString();
      var ab = bp.readByteArray(Math.min(ln, 0x1000));
      if (ab !== null) {
        out.hex = buf2hex(ab);
        try {
          out.text = decodeURIComponent(escape(String.fromCharCode.apply(null, new Uint8Array(ab))));
        } catch (e) {
          /* 非 UTF-8：给可打印视图 */
          var u = new Uint8Array(ab), s = '';
          for (var i = 0; i < u.length; i++) s += (u[i] >= 32 && u[i] < 127) ? String.fromCharCode(u[i]) : '.';
          out.text = '[ascii] ' + s;
        }
      }
      return out;
    } catch (e) { return { err: String(e) }; }
  }

  Interceptor.attach(base.add(ptr(__SEND__)), {
    onEnter: function (args) {
      var rec = { kind: 'send', caller_rva: rvaOf(this.returnAddress) };
      try {
        var sp = args[2];                       // r8 = &shared_ptr<Envelope>
        var env = rd(sp);
        if (env === null || !mapped(env)) { rec.err = 'env unreadable'; send(rec); return; }
        rec.env = env.toString();
        rec.env_vt_rva = rvaOf(rd(env));
        rec.env_type = u32(env.add(0xd8));

        /* 信封自身的 string 字段（已知锚点） */
        rec.env_strings = {};
        [[0x0b0, 'receiver'], [0x600, 'uuid']].forEach(function (kv) {
          rec.env_strings[kv[1]] = readStr(env.add(kv[0]));
        });

        /* 内容对象：body+0x660 = _Ptr, body+0x668 = _Rep */
        var cptr = rd(env.add(0x660));
        var crep = rd(env.add(0x668));
        rec.content_ptr = cptr ? cptr.toString() : null;
        rec.content_rep = crep ? crep.toString() : null;

        var block = null;
        if (cptr && crep) {
          var diff = parseInt(cptr.toString(), 16) - parseInt(crep.toString(), 16);
          rec.ptr_minus_rep = diff;
          if (diff === 0x10) block = crep;
        }
        if (block === null && cptr) block = cptr.sub(0x10);
        rec.block = block ? block.toString() : null;

        if (block && mapped(block)) {
          rec.block_hex = hexOf(block, 0x1b0);
          rec.block_vt_rva = rvaOf(rd(block));
          rec.body_vt_rva = rvaOf(rd(block.add(0x10)));
          rec.refcount = u64(block.add(8));
          rec.is_content_object = (rec.block_vt_rva === __CVT__) && (rec.body_vt_rva === __BVT__);

          /* 全部 12 个 std::string（相对 block，stride 0x20，从 0x20 起） */
          rec.strings = [];
          for (var i = 0; i < 12; i++) {
            var off = 0x20 + i * 0x20;
            var st = readStr(block.add(off));
            st.off = '0x' + off.toString(16);
            rec.strings.push(st);
          }
          rec.i32_0x168 = block.add(0x168).read32();
        }
      } catch (e) { rec.err = String(e); }
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
    want = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    src = (SCRIPT
           .replace("__SEND__", hex(SEND_RVA))
           .replace("__CVT__", f"'0x{CONTENT_VT_RVA:x}'")
           .replace("__BVT__", f"'0x{BODY_VT_RVA:x}'"))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    out = {"sends": []}

    def flush():
        try:
            (OUT_DIR / "string_dump.json").write_text(
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
            print("  钩子就绪（send 入口）", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        out["sends"].append(d)
        flush()
        # 进度：列出已收集的 md5（去重后的真实进度）
        md5s = []
        for s in out["sends"]:
            for st in (s.get("strings") or []):
                if isinstance(st, dict) and st.get("off") == "0x20" and st.get("text"):
                    md5s.append(st["text"])
        print(f"\n=== [send #{len(out['sends'])}] caller_rva={d.get('caller_rva')} "
              f"已收集 md5: {md5s} ===", flush=True)
        print(f"  信封 {d.get('env')} vt_rva={d.get('env_vt_rva')} 类型码={d.get('env_type')}", flush=True)
        for name, st in (d.get("env_strings") or {}).items():
            print(f"    env.{name}: {json.dumps(st, ensure_ascii=False)[:200]}", flush=True)
        print(f"  内容对象 _Ptr={d.get('content_ptr')} _Rep={d.get('content_rep')} "
              f"(ptr-rep={d.get('ptr_minus_rep')})", flush=True)
        print(f"  block={d.get('block')} 控制块vt={d.get('block_vt_rva')} "
              f"体vt={d.get('body_vt_rva')} 引用计数={d.get('refcount')} "
              f"是内容对象={d.get('is_content_object')} i32@0x168={d.get('i32_0x168')}", flush=True)
        for st in d.get("strings") or []:
            if isinstance(st, dict):
                t = st.get("text")
                if t is None:
                    print(f"    {st.get('off')}: len={st.get('len')} cap={st.get('cap')} "
                          f"err={st.get('err')}", flush=True)
                else:
                    print(f"    {st.get('off')}: len={st.get('len')} cap={st.get('cap')} "
                          f"len_text={len(t)} :: {t[:200]!r}", flush=True)
        if d.get("err"):
            print(f"  [err] {d['err']}", flush=True)
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
            if len(out["sends"]) >= want:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\nsend 命中 {len(out['sends'])} 次，写入 {OUT_DIR / 'string_dump.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
