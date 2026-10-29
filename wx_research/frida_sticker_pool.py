"""retain + 延迟重放实验：验证「持有消息对象引用后，过一段时间再提交」是否可行。

背景：
  上一实验证明「同一消息对象重复提交」成立（发2收3），但那是在 onEnter 里
  原地立即重放 —— 对象必然有效。要把它做成「飞栀主动发表情」，对象必须能在
  我这次调用结束之后仍然存活，因此需要 retain 引用计数。

  frida 17 拿不到 kernel32 的 InterlockedIncrement（findExportByName 返回 null），
  所以自写汇编 stub：lock inc dword [rcx]; ret  =>  F0 FF 01 C3

本实验流程：
  1. hook send_commit(0x160ebe0)
  2. 首次捕获时 retain vector 里每个 shared_ptr（stub inc ctrl+8），并保存
     (rcxs, result)
  3. 等待 N 秒（期间微信不断有其他消息/心跳活动，会制造内存压力来暴露"对象已死"）
  4. 通过 rpc 延迟重放一次
  5. 若你收到「第 N 秒后才出现的表情」，说明 retain 生效、模板库方案可行

用法:
    python frida_sticker_pool.py [pid] [delay_seconds]
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
  var COMMIT = base.add(0x160ebe0);
  var CommitFn = new NativeFunction(COMMIT, 'void', ['pointer', 'pointer']);

  // ---- 自写 lock inc stub: F0 FF 01 C3 ----
  var IncFn = null;
  try {
    var stub = Memory.alloc(Process.pageSize);
    stub.writeByteArray([0xF0, 0xFF, 0x01, 0xC3]);
    var protOk = true;
    try { Memory.protect(stub, Process.pageSize, 'rwx'); }
    catch (e) { protOk = false; send({kind:'stub_protect_fail', err: '' + e}); }
    IncFn = new NativeFunction(stub, 'int', ['pointer']);
    var probe = Memory.alloc(4);
    probe.writeU32(41);
    IncFn(probe);
    var got = probe.readU32();
    send({kind:'stub_test', value: got, ok: got === 42, protected: protOk});
  } catch (e) {
    send({kind:'stub_test', ok: false, err: '' + e});
  }

  var saved = null;
  var inReplay = false;
  var hits = 0;
  var retainedCount = 0;

  function retainVec(rcxs) {
    if (IncFn === null) return 0;
    var n = 0;
    try {
      var begin = rcxs.add(8).readPointer();
      var end = rcxs.add(0x10).readPointer();
      var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
      for (var i = 0; i < cnt && i < 8; i++) {
        var ctrl = begin.add(i * 16).add(8).readPointer();
        if (!ctrl.isNull()) { IncFn(ctrl.add(8)); n++; }
      }
    } catch (e) {}
    return n;
  }

  function describe(rcxs) {
    try {
      var begin = rcxs.add(8).readPointer();
      var end = rcxs.add(0x10).readPointer();
      var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
      var out = [];
      for (var i = 0; i < cnt && i < 8; i++) {
        var elem = begin.add(i * 16);
        var obj = elem.readPointer();
        var ctrl = elem.add(8).readPointer();
        var vt = null, refc = null, md5 = null;
        try { vt = obj.readPointer().toString(); } catch (e) {}
        try { refc = ctrl.add(8).readU32(); } catch (e) {}
        // 尝试取子对象里的表情 md5（信封+0x668 → 内容对象 +0x20）
        try {
          var sub = obj.add(0x668).readPointer();
          var len = sub.add(0x20 + 0x10).readU64().toNumber();
          if (len > 0 && len < 64) md5 = sub.add(0x20).readUtf8String(len);
        } catch (e) {}
        out.push({ptr: obj.toString(), ctrl: ctrl.toString(), vt: vt,
                  refcount: refc, md5: md5});
      }
      return out;
    } catch (e) { return ['<err ' + e + '>']; }
  }

  Interceptor.attach(COMMIT, {
    onEnter: function (args) {
      if (inReplay) return;
      hits++;
      if (saved === null) {
        retainedCount = retainVec(args[0]);
        // rcxs 容器本身在提交后会被销毁，所以深拷贝它的 vector 到自有内存，
        // 并自建一个只含 [+8]=begin / [+0x10]=end / [+0x18]=cap 的替身容器。
        var ownRcxs = null;
        try {
          var begin = args[0].add(8).readPointer();
          var end = args[0].add(0x10).readPointer();
          var n = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
          if (n > 0 && n < 64) {
            var vecBuf = Memory.alloc(n * 16);
            vecBuf.writeByteArray(begin.readByteArray(n * 16));
            // ★ 容器缓冲区必须足够大：CALL3 会访问 rcxs+0x4C0 处的字段
            //   （send_text.c 里 rcxs 位于 0x30000 的 arena 内，所以那些偏移
            //    落在已分配内存里，一直没暴露；只给 0x40 就会越界崩溃）
            var RCXS_SIZE = 0x10000;
            ownRcxs = Memory.alloc(RCXS_SIZE);
            ownRcxs.writeByteArray(new Uint8Array(RCXS_SIZE).fill(0));
            ownRcxs.writeByteArray(args[0].readByteArray(0x40));
            ownRcxs.add(8).writePointer(vecBuf);
            ownRcxs.add(0x10).writePointer(vecBuf.add(n * 16));
            ownRcxs.add(0x18).writePointer(vecBuf.add(n * 16));
            send({kind:'own_rcxs', ok: true, ptr: ownRcxs.toString(),
                  size: RCXS_SIZE, vec: vecBuf.toString(), n: n,
                  vtable_field: ownRcxs.readPointer().toString()});
          }
        } catch (e) {
          send({kind:'own_rcxs', ok: false, err: '' + e});
        }
        saved = {rcxs: args[0], ownRcxs: ownRcxs, result: args[1], at: Date.now()};
        // ★ result 不要替换！
        //   实测同一进程内 result 恒为同一个地址（0x85f16fa120 连续三次），
        //   说明它是静态对象、本来就长期有效。
        //   前面几轮把它换成自有副本后，崩溃点都落在 own_result 附近 —— 换掉
        //   一个本来正确的静态指针正是崩溃源头。
        send({kind:'saved', hit: hits, rcxs: args[0].toString(),
              result: args[1].toString(), retained: retainedCount,
              result_is_static: true, vec: describe(args[0])});
      }
    }
  });

  rpc.exports = {
    // 注意：frida 会把下划线方法名转成驼峰，这里直接写成驼峰避免找不到
    sendLater: function () {
      if (saved === null) return {ok: false, why: 'nothing saved'};
      var age = Date.now() - saved.at;
      var useRcxs = saved.ownRcxs !== null ? saved.ownRcxs : saved.rcxs;
      inReplay = true;
      var ok = true, err = null;
      try { CommitFn(useRcxs, saved.result); }   // result 用原值（静态对象）
      catch (e) { ok = false; err = '' + e; }
      inReplay = false;
      return {ok: ok, err: err, age_ms: age,
              used_own_rcxs: saved.ownRcxs !== null,
              rcxs: useRcxs.toString(), result: saved.result.toString()};
    },
    state: function () {
      return {hits: hits, has_saved: saved !== null,
              retained: retainedCount,
              has_own_rcxs: saved !== null && saved.ownRcxs !== null};
    },
    clear: function () { saved = null; inReplay = false; return true; }
  };

  send({kind:'ready'});
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
    delay = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    print(f"attach pid={pid}，retain + 延迟 {delay}s 重放实验", flush=True)
    session = frida.attach(pid)
    state = {"capture": None, "stub": None}

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        if k == "stub_test":
            state["stub"] = d
        elif k == "saved":
            state["capture"] = d
        print(f"  [{k}] {json.dumps(d, ensure_ascii=False)[:600]}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.2)
    st = state.get("stub") or {}
    print(f"  lock-inc stub 自测: {'通过 (41->42)' if st.get('ok') else '失败 ' + str(st)}", flush=True)
    if not st.get("ok"):
        print("  stub 不可用，放弃", flush=True)
        session.detach()
        return 2

    print(f"\n请发一个表情包（捕获后我会等 {delay} 秒再重放）...", flush=True)
    waited = 0.0
    while waited < 600 and state.get("capture") is None:
        time.sleep(0.5)
        waited += 0.5
    if state.get("capture") is None:
        print("未捕获到，退出", flush=True)
        session.detach()
        return 3

    cap = state["capture"]
    print(f"\n已捕获 rcxs={cap['rcxs']} retained={cap['retained']}", flush=True)
    for v in cap.get("vec") or []:
        print(f"  信封 {v}", flush=True)

    try:
        print("  捕获时状态:", script.exports_sync.state(), flush=True)
    except Exception as e:
        print("  state 失败:", e, flush=True)

    print(f"\n等待 {delay} 秒（期间请随意在微信里点点、发发消息制造内存压力）...", flush=True)
    for i in range(delay, 0, -1):
        if i % 5 == 0 or i <= 3:
            try:
                print(f"    剩 {i}s  state={script.exports_sync.state()}", flush=True)
            except Exception:
                pass
        time.sleep(1.0)

    print("\n>>> 延迟重放 ...", flush=True)
    try:
        res = script.exports_sync.send_later()
        print("延迟重放结果:", json.dumps(res, ensure_ascii=False), flush=True)
    except Exception as e:
        print("send_later 调用失败:", type(e).__name__, str(e)[:200], flush=True)
        try:
            res = script.exports_sync.sendLater()
            print("延迟重放结果(驼峰):", json.dumps(res, ensure_ascii=False), flush=True)
        except Exception as e2:
            print("sendLater 也失败:", type(e2).__name__, str(e2)[:200], flush=True)

    time.sleep(4.0)
    print("\n完成 —— 观察微信里是否新出现一条表情", flush=True)
    session.detach()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
