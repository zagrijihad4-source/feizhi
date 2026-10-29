"""建立「构造点 → 提交对象」的完整关联证据。

针对外部复核指出的三个缺陷做了修正：

  1. 不再设 40 条上限（旧脚本 MAXALLOC=40 会截断，导致"未匹配"不可作为结论）
  2. 不再只在 operator new 返回时读内容（那可能是重用存储的旧数据），
     而是直接钩住「写 vtable 到对象」的那一刻 —— 那一刻对象地址是确定的
  3. 不再只比较 P-0x10，而对每个已构造块同时比较 P==B / P==B+0x10 / P==B+0x20

做法：
  - 24 个引用 0x83DCC28 的构造点：用 Instruction.parse 算出 "lea → mov → mov.next"，
    在 mov.next 处下钩子（此时 vtable 刚写进 [reg]）
  - 钩子内扫描通用寄存器，找出 "它的 [0] == base+0x83dcc28" 的那个 → 得到对象地址
  - 同时记录调用者返回地址（构造点的 caller），以及 operator_new(0x1B0) 的分配记录
  - 提交时把 P 与所有已记录块做区间比较，报告匹配关系

用法:
    python frida_sticker_link.py [pid] [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

OUT_DIR = Path(r"<PROJECT_ROOT>\reports")
CONTENT_VTBL_RVA = 0x83DCC28

# 24 个构造点（来自 find_ctor.py 的 lea 地址）
CTOR_LEAS = [
    0x01EF1490, 0x037D1F3B, 0x03ACB0C5, 0x03D67E8E, 0x03DABE22, 0x03DAE6A2,
    0x04018384, 0x0404A881, 0x0404B09C, 0x04317EF1, 0x0455EE0F, 0x04AA72F6,
    0x04AABCDA, 0x04AB6AC5, 0x04AB8F9A, 0x04ABF394, 0x04AC410F, 0x04FBAA5A,
    0x0501E3DC, 0x052D0E5A, 0x05402B82, 0x054053EA, 0x05BB3C25, 0x05BB6B4F,
]

SCRIPT_TMPL = r"""
var MOD = Process.findModuleByName('Weixin.dll');
if (MOD === null) { send({kind:'fatal', err:'no Weixin.dll'}); }
else {
  var base = MOD.base;
  var VT = base.add(__VT__);
  send({kind:'armed', base: base.toString(), vt: VT.toString()});

  var REGS = ['rax','rcx','rdx','rbx','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15'];

  var ctorHits = [];     // {block, rva, caller}
  var allocs = [];       // {block, size, caller}  不设上限
  var MAXLOG = 4000;

  /* 在每个构造点里，算出"mov [reg], vtable"之后的地址，在那里下钩子 */
  var LEAS = __LEAS__;
  var hooked = 0, failed = [];
  LEAS.forEach(function (rva) {
    try {
      var insn = Instruction.parse(base.add(rva));
      var mv = Instruction.parse(insn.next);
      var after = mv.next;
      Interceptor.attach(after, {
        onEnter: function () {
          if (ctorHits.length >= MAXLOG) return;
          var c = this.context;
          for (var i = 0; i < REGS.length; i++) {
            var r = REGS[i];
            try {
              var p = c[r];
              if (!p || p.isNull()) continue;
              var v = p.readPointer();
              if (v.equals(VT)) {
                ctorHits.push({block: p.toString(), rva: rva.toString(16),
                               caller: this.returnAddress.toString()});
                send({kind:'ctor_hit', block: p.toString(), ctor_rva: rva.toString(16),
                      caller: this.returnAddress.toString(), via_reg: r});
                break;
              }
            } catch (e) {}
          }
        }
      });
      hooked++;
    } catch (e) { failed.push(rva.toString(16) + ':' + e); }
  });
  send({kind:'ctors', hooked: hooked, total: LEAS.length, failed: failed});

  /* 分配记录（不设上限），额外记录调用者 */
  try {
    Interceptor.attach(base.add(0x64a7d1c), {
      onEnter: function (args) { this.size = args[0].toInt32(); },
      onLeave: function (ret) {
        if (allocs.length >= MAXLOG) return;
        if (this.size !== 0x1B0 && this.size !== 0x1A0 && this.size !== 0x170 && this.size !== 0x160) return;
        allocs.push({block: ret.toString(), size: this.size,
                     caller: this.returnAddress.toString()});
        send({kind:'alloc', block: ret.toString(), size: this.size,
              caller: this.returnAddress.toString()});
      }
    });
    send({kind:'hooked', name:'operator_new'});
  } catch (e) { send({kind:'hookfail', name:'operator_new', err:''+e}); }

  /* 提交：把 P 与已记录的构造块/分配块做比较 */
  try {
    Interceptor.attach(base.add(0x160ebe0), {
      onEnter: function (args) {
        var rec = {kind:'commit', rcxs: args[0].toString(), objs: []};
        try {
          var begin = args[0].add(8).readPointer();
          var end = args[0].add(0x10).readPointer();
          var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
          for (var i = 0; i < cnt && i < 3; i++) {
            var env = begin.add(i * 16).readPointer();
            var o = {env: env.toString()};
            try { o.env_vt = env.readPointer().toString(); } catch (e) {}
            try {
              var P = env.add(0x668).readPointer();
              o.P = P.toString();
              o.P_vt = (function(){ try { return P.readPointer().toString(); } catch(e){ return null; } })();
              o.P_at_0x670 = env.add(0x670).readPointer().toString();
              // 与构造点记录比较
              o.matched_ctor = null;
              for (var k = 0; k < ctorHits.length; k++) {
                try {
                  var b = ptr(ctorHits[k].block);
                  if (b.equals(P)) { o.matched_ctor = {how:'P==B', rva: ctorHits[k].rva}; break; }
                  if (b.add(0x10).equals(P)) { o.matched_ctor = {how:'P==B+0x10', rva: ctorHits[k].rva}; break; }
                  if (b.add(0x20).equals(P)) { o.matched_ctor = {how:'P==B+0x20', rva: ctorHits[k].rva}; break; }
                  if (b.sub(0x10).equals(P)) { o.matched_ctor = {how:'P==B-0x10', rva: ctorHits[k].rva}; break; }
                } catch (e) {}
              }
              // 与分配记录比较
              o.matched_alloc = null;
              for (var m = 0; m < allocs.length; m++) {
                try {
                  var ab = ptr(allocs[m].block);
                  if (ab.equals(P)) { o.matched_alloc = {how:'P==alloc', size: allocs[m].size}; break; }
                  if (ab.add(0x10).equals(P)) { o.matched_alloc = {how:'P==alloc+0x10', size: allocs[m].size}; break; }
                } catch (e) {}
              }
            } catch (e) { o.perr = '' + e; }
            rec.objs.push(o);
          }
        } catch (e) { rec.err = '' + e; }
        rec.ctor_count = ctorHits.length;
        rec.alloc_count = allocs.length;
        send(rec);
      }
    });
    send({kind:'hooked', name:'commit'});
  } catch (e) { send({kind:'hookfail', name:'commit', err:''+e}); }
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
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = (SCRIPT_TMPL
           .replace("__VT__", hex(CONTENT_VTBL_RVA))
           .replace("__LEAS__", json.dumps([hex(x) for x in CTOR_LEAS])))
    print(f"attach pid={pid}，建立构造→提交关联，最长 {seconds}s", flush=True)
    session = frida.attach(pid)
    records = []
    state = {"base": None, "ctor_hits": [], "allocs": []}

    def flush():
        try:
            (OUT_DIR / "sticker_link.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("  [落盘失败]", e, flush=True)

    def to_rva(a):
        try:
            b = state["base"]
            return hex(int(a, 16) - int(b, 16)) if b and a else None
        except Exception:
            return None

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:200], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "armed":
            state["base"] = d["base"]
            print(f"  base={d['base']}  VT={d['vt']} (RVA {hex(CONTENT_VTBL_RVA)})", flush=True)
            return
        if k == "ctors":
            print(f"  构造点挂钩: {d['hooked']}/{d['total']} 个成功"
                  + (f"，失败 {d['failed']}" if d.get("failed") else ""), flush=True)
            return
        if k in ("hooked", "hookfail", "fatal"):
            print(f"  {k}: {d.get('name') or d.get('err')}", flush=True)
            return
        if k == "alloc":
            state["allocs"].append(d)
            return
        if k == "ctor_hit":
            state["ctor_hits"].append(d)
            flush()
            print(f"  [构造] block={d['block']} RVA={to_rva(d['block'])} "
                  f"ctor_rva={d['ctor_rva']} reg={d['via_reg']} caller={to_rva(d['caller'])}", flush=True)
            return
        records.append(d)
        if k == "commit":
            flush()
            print(f"\n=== [COMMIT] 构造记录 {d.get('ctor_count')} 条 / 分配记录 {d.get('alloc_count')} 条 ===", flush=True)
            for o in d.get("objs", []):
                print(f"  信封 {o.get('env')} vt_rva={to_rva(o.get('env_vt'))}", flush=True)
                print(f"    P = {o.get('P')}  RVA={to_rva(o.get('P'))}  P_vt_rva={to_rva(o.get('P_vt'))}", flush=True)
                print(f"    P+8([env+0x670]) = {o.get('P_at_0x670')}", flush=True)
                print(f"    ★ 匹配构造点: {o.get('matched_ctor')}", flush=True)
                print(f"    ★ 匹配分配块: {o.get('matched_alloc')}", flush=True)

    script = session.create_script(src)
    script.on("message", on_message)
    script.load()
    time.sleep(1.0)
    print("\n已就绪 —— 请发一个收藏表情", flush=True)
    started = time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(0.5)
            if any(r.get("kind") == "commit" for r in records):
                time.sleep(1.0)
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        print(f"\n构造记录 {len(state['ctor_hits'])} 条 / 分配记录 {len(state['allocs'])} 条，"
              f"写入 {OUT_DIR / 'sticker_link.json'}", flush=True)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
