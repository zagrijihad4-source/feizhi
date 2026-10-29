"""一次性采样：记录对象原始数据 + 内容对象完整字节。

背景（静态分析结论，见 reports/ctor_3d67da0.asm）：
  0x3D67DA0(rcx=&out_vector, rdx=&shared_ptr<Record>)
  遍历 Record.+0x70 的 vector，每条：
      block = operator new(0x1B0)          # 0x64A7D1C
      [block + 0x00] = 0x83DCC28           # std::_Ref_count_obj2<T> 控制块 vtable
      [block + 0x08] = 0x100000001         # _Uses=1, _Weaks=1
      memset(block + 0x18, 0, 0x158)
      [block + 0x10] = 0x8755528           # 业务对象真 vtable（对象体起点 = block+0x10）
      10 个 std::string @ block + 0x20 .. 0x140（stride 0x20: buf/len/cap）
      [block + 0x168] = -1
      string @ block + 0x170, 0x190
      输出 shared_ptr{ptr = block + 0x10, refctrl = block}

本脚本要产出（全部来自一次真实发送）：
  1. Record 对象（`[记录+0x70]` vector 的元素）原始字节 —— 判断能否枚举整个收藏库
  2. 新建 0x1B0 块的完整字节 + 12 个 string 的实际内容 —— 用于静态重放
  3. 提交点 0x160EBE0 收到的 vector 元素，确认信封拿到的对象体指针
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")

FACTORY_RVA = 0x3D67DA0
PUSHBACK_RVA = 0x3D6828D
COMMIT_RVA = 0x160EBE0
BLOCK_SIZE = 0x1B0

SCRIPT = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  send({kind:'armed', base: base.toString()});

  var MAXLOG = 200;
  var blocks = [];       // {addr, seq}  本次采样内新建的 0x1B0 块
  var pending = [];      // factory 调用上下文栈
  var log = [];

  function hex(ptr, n) {
    try { var b = ptr.readByteArray(n); if (b === null) return null;
          return buf2hex(b); } catch (e) { return null; }
  }
  function buf2hex(ab) {
    var u = new Uint8Array(ab), s = '';
    for (var i = 0; i < u.length; i++) {
      s += (u[i] < 16 ? '0' : '') + u[i].toString(16);
    }
    return s;
  }
  /* MSVC std::string：buf@+0, len@+0x10, cap@+0x18；cap<=0xF 时 buf 为内联 */
  function readStr(ptr) {
    try {
      var cap = ptr.add(0x18).readU64().toNumber();
      var len = ptr.add(0x10).readU64().toNumber();
      if (len <= 0 || len > 0x10000) return null;
      if (cap <= 0xf) {
        var ab = ptr.readByteArray(Math.min(len, 0x100));
        return ab ? utf8(ab) : null;
      }
      var p = ptr.readPointer();
      var ab2 = p.readByteArray(Math.min(len, 0x100));
      return ab2 ? utf8(ab2) : null;
    } catch (e) { return null; }
  }
  function utf8(ab) {
    try { return decodeURIComponent(escape(String.fromCharCode.apply(
      null, new Uint8Array(ab).subarray(0, 512)))); } catch (e) { return null; }
  }
  function readU32(ptr) { try { return ptr.readU32(); } catch (e) { return null; } }
  function readU64(ptr) { try { return ptr.readU64().toString(); } catch (e) { return null; } }
  function fld(obj, off) {
    try { return obj.add(off).readPointer().toString(); } catch (e) { return null; }
  }

  /* ---- 1) push_back 点：0x3D6828D `add qword [rax+8],0x10`
         此刻 [rbp+0x100] = 对象体指针（= block+0x10），故 block = [rbp+0x100] - 0x10。
         不 hook operator new（热路径，开销不可接受）。 ---- */
  Interceptor.attach(base.add(__PUSHBACK__), {
    onEnter: function () {
      try {
        var body = this.context.rbp.add(0x100).readPointer();
        if (!body.isNull()) {
          blocks.push({ addr: body.sub(0x10).toString(), body: body.toString(),
                        seq: blocks.length });
        }
      } catch (e) {}
      if (blocks.length > 64) blocks.splice(0, blocks.length - 64);
    }
  });

  /* ---- 2) 工厂：进入时抓 Record，离开时抓新建块 ---- */
  Interceptor.attach(base.add(__FACTORY__), {
    onEnter: function (args) {
      var outVec = args[0];              // &vector<shared_ptr<T>>
      var sp = args[1];                  // &shared_ptr<Record>
      var rec = null, refc = null;
      try { rec = sp.readPointer(); refc = sp.add(Process.pointerSize).readPointer(); } catch (e) {}
      var recInfo = null;
      if (rec !== null && !rec.isNull()) {
        var vb = fld(rec, 0x70), cnt = readU32(rec.add(0x78));
        var vd = fld(rec, 0x90), cnt2 = readU32(rec.add(0x98));
        var elems = [];
        if (vb !== null && cnt !== null && cnt > 0 && cnt < 64) {
          try {
            var bp = ptr(vb);
            for (var i = 0; i < cnt; i++) {
              var e = bp.add(i * 8).readPointer();
              elems.push({ p: e.toString(), hex: hex(e, 0x80) });
            }
          } catch (e) {}
        }
        var elems2 = [];
        if (vd !== null && cnt2 !== null && cnt2 > 0 && cnt2 < 64) {
          try {
            var bp2 = ptr(vd);
            for (var j = 0; j < cnt2; j++) {
              var e2 = bp2.add(j * 8).readPointer();
              elems2.push({ p: e2.toString(), hex: hex(e2, 0x80) });
            }
          } catch (e) {}
        }
        recInfo = {
          rec: rec.toString(),
          obj_hex: hex(rec, 0x200),
          cnt_0x6c: readU32(rec.add(0x6c)),
          cnt_0xa8: readU32(rec.add(0xa8)),
          vec_0x70: vb, n_0x70: cnt, elems_0x70: elems,
          vec_0x90: vd, n_0x90: cnt2, elems_0x90: elems2,
          refc: refc === null ? null : refc.toString()
        };
      }
      this.outVec = outVec.toString();
      this.recInfo = recInfo;
      this.mark = blocks.length;
    },
    onLeave: function (ret) {
      var made = blocks.slice(this.mark);
      var objs = [];
      for (var i = 0; i < made.length && i < 16; i++) {
        var b = ptr(made[i].addr);
        var strs = [];
        for (var k = 0; k < 12; k++) {
          strs.push(readStr(b.add(0x20 + k * 0x20)));
        }
        objs.push({
          block: made[i].addr,
          body: b.add(0x10).toString(),
          vt_ctl: fld(b, 0),
          vt_body: fld(b, 0x10),
          refcnt: readU64(b.add(8)),
          i32_0x168: readU32(b.add(0x168)),
          strings: strs,
          md5_0x20: readStr(b.add(0x20)),
          s_0x60: readStr(b.add(0x60)),
          s_0xe0: readStr(b.add(0xe0)),
          s_0x100: readStr(b.add(0x100)),
          s_0x120: readStr(b.add(0x120)),
          s_0x140: readStr(b.add(0x140)),
          s_0x170: readStr(b.add(0x170)),
          s_0x190: readStr(b.add(0x190)),
          hex: hex(b, __BS__)
        });
      }
      log.push({ kind: 'factory', outVec: this.outVec, rec: this.recInfo, made: objs });
      send({ kind: 'factory', count: objs.length, rec: this.recInfo, made: objs });
    }
  });

  /* ---- 3) 提交点：确认信封拿到的对象体指针 ---- */
  Interceptor.attach(base.add(__COMMIT__), {
    onEnter: function (args) {
      var vec = args[0];               // &vector<shared_ptr<T>>
      var env = args[1];               // 信封
      var vb = fld(vec, 0), ve = fld(vec, 0x8);
      var cnt = null;
      try {
        if (vb !== null && ve !== null) {
          cnt = (parseInt(ve, 16) - parseInt(vb, 16)) / 16;
          if (!isFinite(cnt) || cnt < 0 || cnt > 64) cnt = null;
        }
      } catch (e) { cnt = null; }
      var items = [];
      if (vb !== null && cnt !== null && cnt >= 0 && cnt < 64) {
        try {
          for (var i = 0; i < cnt; i++) {
            var sp = ptr(vb).add(i * 16);
            items.push({ ptr: fld(sp, 0), refc: fld(sp, 8) });
          }
        } catch (e) {}
      }
      var envContent = null, envDump = null;
      if (env !== null && !env.isNull()) {
        // 只在确认目标地址已映射时才读，避免越界访问搞崩微信
        try {
          if (Process.findRangeByAddress(env.add(0x668)) !== null) {
            envContent = fld(env, 0x668);
          }
          if (Process.findRangeByAddress(env) !== null) {
            envDump = hex(env, 0x110);
          }
        } catch (e) { envContent = null; }
      }
      var info = {
        kind: 'commit',
        vec: vec.toString(), env: env === null ? null : env.toString(),
        n: cnt, items: items, env_0x668: envContent, env_dump: envDump,
        env_vt: env.isNull() ? null : fld(env, 0)
      };
      log.push(info);
      send(info);
    }
  });

  send({ kind: 'hooks_ok' });
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

    src = (SCRIPT
           .replace("__PUSHBACK__", hex(PUSHBACK_RVA))
           .replace("__FACTORY__", hex(FACTORY_RVA))
           .replace("__COMMIT__", hex(COMMIT_RVA))
           .replace("__BS__", str(BLOCK_SIZE)))

    print(f"attach pid={pid}，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    found = {"factories": [], "commits": []}

    def on_message(msg, data=None):
        if msg.get("type") == "error":
            print("  [script error]", msg.get("description"), flush=True)
            if msg.get("stack"):
                print("   ", msg["stack"][:400], flush=True)
            return
        if msg.get("type") != "send":
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            print(f"  base={d['base']}", flush=True)
            return
        if k == "hooks_ok":
            print("  钩子就绪：operator new / 工厂 / 提交点", flush=True)
            return
        if k == "fatal":
            print("  [fatal]", d.get("err"), flush=True)
            return
        if k == "factory":
            found["factories"].append(d)
            (OUT_DIR / "sticker_full.json").write_text(
                json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n=== [工厂] 新建 {d['count']} 个内容对象 ===", flush=True)
            r = d.get("rec")
            if r:
                print(f"  Record = {r['rec']}  cnt(+0x6c)={r['cnt_0x6c']} "
                      f"cnt(+0xa8)={r['cnt_0xa8']}", flush=True)
                print(f"  vec(+0x70) n={r['n_0x70']}  vec(+0x90) n={r['n_0x90']}", flush=True)
                for i, e in enumerate(r.get("elems_0x70") or []):
                    h = e.get("hex") or ""
                    print(f"    vec0x70[{i}] {e['p']} hex[:64]={h[:64]}", flush=True)
                for i, e in enumerate(r.get("elems_0x90") or []):
                    h = e.get("hex") or ""
                    print(f"    vec0x90[{i}] {e['p']} hex[:64]={h[:64]}", flush=True)
            for o in d.get("made") or []:
                print(f"  --- block={o['block']} body={o['body']} "
                      f"vt_ctl={o['vt_ctl']} vt_body={o['vt_body']} ref={o['refcnt']}", flush=True)
                for i, s in enumerate(o.get("strings") or []):
                    if s:
                        print(f"      str[{(0x20+i*0x20):#04x}] = {s[:180]}", flush=True)
            return
        if k == "commit":
            found["commits"].append(d)
            (OUT_DIR / "sticker_full.json").write_text(
                json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n=== [提交] 信封 {d['env']} vt={d['env_vt']} ===", flush=True)
            print(f"  vector n={d['n']}  env+0x668={d['env_0x668']}", flush=True)
            for i, it in enumerate(d.get("items") or []):
                print(f"    item[{i}] ptr={it['ptr']} refc={it['refc']}", flush=True)
            return

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请发送一个收藏表情", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if found["factories"]:
                time.sleep(2.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass
        print(f"\n工厂命中 {len(found['factories'])} 次 / 提交 {len(found['commits'])} 次，"
              f"写入 {OUT_DIR / 'sticker_full.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
