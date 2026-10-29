"""重放实验：验证「已构造好的表情消息对象」能否被重复提交。

依据（全部来自实测）：
  - 表情内容的 md5 / filekey / storeid 本地可复用，两次发送逐字节相同
    （只有信封 +0x600 的消息 UUID 每次新生成）
  - send_commit(0x160ebe0) 的参数 rcxs 是消息容器：
    [rcxs+8]=vector.begin, [rcxs+0x10]=vector.end, 元素 16 字节 shared_ptr
    （[0]=T*, [8]=控制块，引用计数在 ctrl+8）

做法：
  hook 0x160ebe0 首次触发时保存 (rcxs, result)，并对 vector 里每个 shared_ptr
  调用 InterlockedIncrement 增加引用计数（防止提交后对象被释放）；
  随后通过 rpc.exports.replay() 主动再提交一次。

如果重放成功，说明可以绕过「找发送入口」这一步 —— 直接复用微信自己构造的消息对象。

用法:
    python frida_sticker_replay.py [pid] [seconds]
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
  send({kind:'armed', base: base.toString()});

  var InterlockedIncrement = null;
  try {
    var k32 = Process.getModuleByName('kernel32.dll');
    var p = k32.findExportByName('InterlockedIncrement');
    if (p) InterlockedIncrement = new NativeFunction(p, 'int', ['pointer']);
  } catch (e) {}

  var CommitFn = new NativeFunction(COMMIT, 'void', ['pointer', 'pointer']);

  var saved = null;
  var inReplay = false;
  var hits = 0;

  function descVec(rcxs) {
    try {
      var begin = rcxs.add(8).readPointer();
      var end = rcxs.add(0x10).readPointer();
      var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
      var out = [];
      for (var i = 0; i < cnt && i < 8; i++) {
        var elem = begin.add(i * 16);
        var obj = elem.readPointer();
        var ctrl = elem.add(8).readPointer();
        var vt = null;
        try { vt = obj.readPointer().toString(); } catch (e) {}
        out.push({ptr: obj.toString(), ctrl: ctrl.toString(), vt: vt});
      }
      return out;
    } catch (e) { return ['<err ' + e + '>']; }
  }

  function retainVec(rcxs) {
    if (InterlockedIncrement === null) return 0;
    var n = 0;
    try {
      var begin = rcxs.add(8).readPointer();
      var end = rcxs.add(0x10).readPointer();
      var cnt = Math.floor(Math.abs(end.sub(begin).toInt32()) / 16);
      for (var i = 0; i < cnt && i < 8; i++) {
        var ctrl = begin.add(i * 16).add(8).readPointer();
        if (!ctrl.isNull()) { InterlockedIncrement(ctrl.add(8)); n++; }
      }
    } catch (e) {}
    return n;
  }

  Interceptor.attach(COMMIT, {
    onEnter: function (args) {
      if (inReplay) return;                 // 重放触发的调用，不再保存/不再重放
      hits++;
      if (saved === null) {
        saved = {rcxs: args[0], result: args[1]};
        send({kind:'captured', hit: hits, rcxs: args[0].toString(),
              result: args[1].toString(), retained: 0,
              vec: descVec(args[0])});
        // 不持有引用，改为在此刻立即重放 —— 对象必然有效、且同线程
        inReplay = true;
        try {
          CommitFn(args[0], args[1]);
          send({kind:'replayed_now', ok: true});
        } catch (e) {
          send({kind:'replayed_now', ok: false, err: '' + e});
        }
        inReplay = false;
      } else {
        send({kind:'again', hit: hits, rcxs: args[0].toString()});
      }
    }
  });

  rpc.exports = {
    replay: function () {
      return {ok: false, why: 'already auto-replayed on capture'};
    },
    state: function () {
      return {has_saved: saved !== null, hits: hits,
              rcxs: saved ? saved.rcxs.toString() : null};
    }
  };

  send({kind:'ready', interlocked: InterlockedIncrement !== null});
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
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"attach pid={pid}，重放实验挂载中 ...", flush=True)
    session = frida.attach(pid)
    state = {}

    def on_message(msg, data=None):
        if msg.get("type") != "send":
            print("  [msg]", str(msg)[:300], flush=True)
            return
        d = msg["payload"]
        k = d.get("kind")
        state["last"] = d
        if k == "captured":
            state["capture"] = d
        print(f"  [{k}] {json.dumps(d, ensure_ascii=False)[:500]}", flush=True)

    script = session.create_script(SCRIPT)
    script.on("message", on_message)
    script.load()
    time.sleep(1.2)
    print(f"  interlocked 可用: {state.get('last', {}).get('interlocked')}", flush=True)
    print("\n请发一个表情（捕获对象后我会自动重放一次）...", flush=True)

    # 等待首次捕获 + 自动重放结果
    waited = 0.0
    got_capture = False
    got_replay = None
    while waited < seconds:
        last = state.get("last", {})
        if last.get("kind") == "captured":
            got_capture = True
        if last.get("kind") == "replayed_now":
            got_replay = last
        if got_capture and got_replay is not None:
            break
        time.sleep(0.5)
        waited += 0.5

    if not got_capture:
        print("未捕获到提交，退出", flush=True)
        session.detach()
        return 2

    cap = state.get("capture") or {}
    print("\n已捕获并自动重放完毕。", flush=True)
    if got_replay is not None:
        print("重放结果:", json.dumps(got_replay, ensure_ascii=False), flush=True)
    else:
        print("未观察到重放结果事件（可能重放时崩溃或未执行）", flush=True)

    time.sleep(3.0)
    try:
        st = script.exports_sync.state()
        print("最终状态:", st, flush=True)
    except Exception:
        pass
    print("\n完成 —— 观察微信里是否多出一条相同表情", flush=True)
    session.detach()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
