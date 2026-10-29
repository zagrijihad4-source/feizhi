"""任务上下文复用实验 —— 目标：免点击自动发送收藏表情。

背景
----
载体替换（frida_sticker_swap.py）已打通「点一次发任意表情」，但每次仍需人工点击。
手工构造路线（DLL type=8 / type=4）之所以「发送失败」，本文件把它定位到了确切的
一行：#26.2 已证明失败在「承载内容的那套上下文」，而 wxb_send_sticker_pack 调用
0xDB40 时第 5 参数传的是：

    d4 = arena + 0x0A80      /* 一个 ZeroMemory 过的假上下文 */

0xDB40 会把 [d4] / [d4+8] 原样搬进 cfg[0] / cfg[8]。自然发送时这两个值是真实的
shared_ptr<TaskContext>（cfg[0]=body, cfg[8]=ctrl, 且 ctrl+0x10 == body）。

本实验
------
    hook 0x160EBE0(pack)   —— 自然发送时捕获真实 cfg[0]/cfg[8]
    hook 0xDB40            —— 我们的发送到达时，把 d4 指向的内存注入真实值

判定标准
--------
  · DLL type=8 发送后对端收到表情  ⇒ 任务上下文可复用 ⇒「点一次、之后全自动」成立
  · 仍然「发送失败」              ⇒ 上下文与单次发送绑定 ⇒ 转 1b：上溯更少参数的入口

安全设计
--------
  · 只读写 arena 里的 16 字节（我们自己的 VirtualAlloc 区），不碰任何微信对象
  · 注入前先探测真实 body 是否仍可读；不可读则跳过（避免野指针）
  · 捕获只发生在 cfg[0] 与 cfg[8] 双非空、且 ctrl+0x10 == body 时（自然发送的特征）

用法
----
    python frida_ctx_reuse.py                 # 捕获 + 自动触发 type=8 发送
    python frida_ctx_reuse.py --no-autosend   # 只捕获，不发送
    python frida_ctx_reuse.py --target wxid_xxx --seconds 1200
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

REPORTS = Path(r"<PROJECT_ROOT>\reports")
BRIDGE = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge")
OUTBOX = BRIDGE / "outbox" / "next.txt"
CONTROL = BRIDGE / "control"

JS_TEMPLATE = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = __OUT__;
const AUTOSEND = __AUTOSEND__;
const MAX_CAPTURES = 3;

function w(line) {
    try {
        const f = new File(OUT, "a");
        f.write(line + "\n");
        f.flush();
        f.close();
    } catch (e) {}
}

function rva(p) {
    try { return "0x" + p.sub(base).toString(16); } catch (e) { return "?"; }
}

function readable(p, n) {
    try {
        const b = p.readByteArray(n);
        return b !== null;
    } catch (e) { return false; }
}

function hexOf(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n)))
            .map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    } catch (e) { return "ERR " + e; }
}

let realBody = null;   // NativePointer
let realCtrl = null;
let captures = 0;
let injected = 0;
let packHits = 0;
let emojiHits = 0;

// 信封组 d1 的 vtable RVA（表情路径）。只在它出现时才注入，
// 避免污染文本组（0x83661E8）等其它消息的发送。
const VT_ENV_D1 = "0x83677e8";
// 任务上下文控制块的 vtable RVA（§20.5 实测值）。用它做「对象是否仍有效」的判据：
// body 的首字段会随内存复用而变（不可用），但 ctrl 的 vtable 在对象存活期稳定。
const CTRL_VT = "0x7f5f398";

w("== ctx-reuse loaded base=" + base.toString() + " ==");

/* 心跳：证明 agent 活着，并能区分「没被调用」与「调用了但没捕获」 */
setInterval(function () {
    w("TICK packHits=" + packHits + " emojiHits=" + emojiHits +
      " captures=" + captures + " injected=" + injected);
}, 5000);

/* ---- 1) 捕获：pack 入口读 cfg[0] / cfg[8] ---- */
Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        // 无条件记录前几次调用——这是区分"没走到这里"与"走到了但 cfg 为空"的唯一手段
        packHits++;
        if (packHits <= 6) {
            try {
                w("PACK#" + packHits + " tid=" + Process.getCurrentThreadId() +
                  " cfg=" + args[1] +
                  " cfg0=" + args[1].readPointer() +
                  " cfg8=" + args[1].add(8).readPointer());
            } catch (e1) { w("PACK#" + packHits + " dump ERR " + e1); }
        }
        if (captures >= MAX_CAPTURES) return;
        try {
            const cfg = args[1];
            if (cfg.isNull()) return;
            const body = cfg.readPointer();
            const ctrl = cfg.add(8).readPointer();
            if (body.isNull() || ctrl.isNull()) return;
            // 控制块布局（§8.3 实测）：[0]=vtbl, [8]=_Uses, [0xc]=_Weaks，
            // 对象体 = 块 + 0x10 —— 是「紧邻」，不是在 +0x10 处存对象体指针。
            // 上一版写成 ctrl.add(0x10).readPointer() 解引用，条件恒为假，captures 一直为 0。
            if (!ctrl.add(0x10).equals(body)) {
                if (packHits <= 6) {
                    w("  capture SKIP: body=" + body + " ctrl=" + ctrl +
                      " ctrl+0x10=" + ctrl.add(0x10) + " (不构成 shared_ptr)");
                }
                return;
            }
            // 再确认 body 可读且首 qword 像指针
            if (!readable(body, 0x40)) return;

            realBody = body;
            realCtrl = ctrl;
            captures++;
            w("CAPTURE#" + captures + " tid=" + Process.getCurrentThreadId() +
              " cfg=" + cfg + " body=" + body + " ctrl=" + ctrl +
              " body_vt=" + rva(body.readPointer()) +
              " ctrl_vt=" + rva(ctrl.readPointer()));

            /* 顺便 dump 内容对象，用来识别这到底是哪个表情（收藏 / 表情包 / 商店）。
             * 布局见 TASK_LOG §26.3：信封 +0x660 → 对象体 vtable 0x8755528，
             * 六个有效槽 slot0/2/6/7/8/9。若新表情的槽位与此同构，就说明
             * 同一套发送方式可以覆盖它。 */
            try {
                const b = args[0].add(8).readPointer();
                const e = args[0].add(0x10).readPointer();
                const nm = e.sub(b).toInt32() / 16;
                if (nm > 0 && nm < 8) {
                    const m = b.readPointer();
                    if (rva(m.readPointer()) === "0x82cb8d8") {
                        const cb = m.add(0x660).readPointer();
                        if (!cb.isNull() && rva(cb.readPointer()) === "0x8755528") {
                            const slots = {};
                            for (let k = 0; k < 12; k++) {
                                const off = 0x10 + k * 0x20;
                                let len = 0, cap = 0, txt = "";
                                try {
                                    len = cb.add(off + 0x10).readInt();
                                    cap = cb.add(off + 0x18).readInt();
                                    if (len > 0 && len < 8192) {
                                        const buf = (cap <= 0xf)
                                            ? cb.add(off) : cb.add(off).readPointer();
                                        if (!buf.isNull()) txt = buf.readUtf8String(len);
                                    }
                                } catch (es) {}
                                slots["slot" + k] = txt;
                            }
                            // 收藏表情的布局只用到 0/2/6/7/8/9；其它类型（表情包/商店）
                            // 可能把字段放在别的槽上，所以这里 12 个槽全部记录。
                            let summary = "";
                            for (let k = 0; k < 12; k++) {
                                const t = slots["slot" + k];
                                if (t) summary += " s" + k + "(len=" + t.length + ")";
                            }
                            w("  CONTENT 非空槽:" + (summary || " <全空>"));
                            // 完整对象体 hex：用来和收藏表情的布局逐字段对照，
                            // 判断非字符串字段（类型/整数字段）是否也需要区分
                            w("    body_hex=" + hexOf(cb, 0x1B0));
                            for (let k = 0; k < 12; k++) {
                                const t = String(slots["slot" + k] || "");
                                if (t) w("    slot" + k + " = " + t.substring(0, 220));
                            }
                            send({ ev: "content", slots: slots });
                        }
                    }
                }
            } catch (eC) { w("  content dump ERR " + eC); }

            send({ ev: "captured", body: body.toString(),
                   ctrl: ctrl.toString(), n: captures });
        } catch (e) {
            w("capture ERR " + e);
        }
    }
});
w("attached pack 0x160EBE0 (capture)");

/* ---- 2) 注入：0xDB40 入口，d4 为全零假上下文时写入真实值 ---- */
Interceptor.attach(base.add(0xDB40), {
    onEnter(args) {
        try {
            if (realBody === null || realCtrl === null) return;
            // 只处理信封组委托（表情路径）
            try {
                if (rva(args[1].readPointer()) !== VT_ENV_D1) return;
            } catch (e0) { return; }
            const d4 = args[4];
            if (d4.isNull()) return;
            const v0 = d4.readPointer();
            const v1 = d4.add(8).readPointer();
            // 只接管「全零块」——即 DLL 自己那套 arena 假上下文
            if (!(v0.isNull() && v1.isNull())) return;
            // 存活探测一：内存可读
            if (!readable(realBody, 0x40)) {
                w("INJECT SKIP: realBody 已不可读 " + realBody);
                send({ ev: "inject_skip", reason: "body_unreadable" });
                return;
            }
            // 存活探测二：控制块 vtable 未变（对象没被释放/复用）
            try {
                const cvt = rva(realCtrl.readPointer());
                if (cvt !== CTRL_VT) {
                    w("INJECT SKIP: ctrl_vt=" + cvt + " 期望 " + CTRL_VT +
                      " -> 上下文已失效");
                    send({ ev: "inject_skip", reason: "ctrl_vt_changed:" + cvt });
                    return;
                }
            } catch (e2) {
                w("INJECT SKIP: ctrl vtable 读取失败 " + e2);
                send({ ev: "inject_skip", reason: "ctrl_vt_unreadable" });
                return;
            }
            d4.writePointer(realBody);
            d4.add(8).writePointer(realCtrl);
            injected++;
            w("INJECT#" + injected + " tid=" + Process.getCurrentThreadId() +
              " d4=" + d4 + " <- body=" + realBody + " ctrl=" + realCtrl);
            send({ ev: "injected", d4: d4.toString(), n: injected });
        } catch (e) {
            w("inject ERR " + e);
        }
    }
});
w("attached db40 0xDB40 (inject)");

/* ---- 2b) 观察 emoji_ctor：自然发送收藏表情的必经入口（§20.2 实测） ---- */
Interceptor.attach(base.add(0x160DF80), {
    onEnter(args) {
        emojiHits++;
        if (emojiHits <= 6) {
            w("EMOJI_CTOR#" + emojiHits + " tid=" + Process.getCurrentThreadId() +
              " rcx=" + args[0] + " rdx=" + args[1] + " r8=" + args[2] + " r9=" + args[3]);
        }
    }
});
w("attached emoji_ctor 0x160DF80 (observe)");

/* ---- 3) 周期性存活探测 ---- */
setInterval(function () {
    if (realBody === null) { return; }
    const ok = readable(realBody, 0x40);
    w("PROBE tid=" + Process.getCurrentThreadId() + " body=" + realBody +
      " alive=" + ok +
      (ok ? " vt=" + rva(realBody.readPointer()) : ""));
}, 5000);
"""


def build_js(out_path: Path, autosend: bool) -> str:
    js = JS_TEMPLATE
    js = js.replace("__OUT__", json.dumps(str(out_path)))
    js = js.replace("__AUTOSEND__", "true" if autosend else "false")
    return js


def write_outbox(seq: str, to_wxid: str, tpl: int, cmd_type: int = 8) -> None:
    """铁律：写之前先清空，避免残留命令被新 worker 立刻执行。

    cmd_type = 8  收藏表情（type=8）
    cmd_type = 12 表情包（表情商店）表情（type=12）
    """
    OUTBOX.write_text("", encoding="utf-8")
    time.sleep(0.3)
    OUTBOX.write_text(f"{seq}\t{cmd_type}\t{to_wxid}\t{tpl}\n", encoding="utf-8")


def read_result(seq: str) -> str:
    p = CONTROL / f"result_{seq}.json"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace").strip()
    return "(no result file)"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    argv = sys.argv[1:]
    autosend = "--no-autosend" not in argv
    # --dump-ctx：捕获后把 body/ctrl 落盘到 control\ctx_override.txt，供 DLL 读取注入
    dump_ctx = "--dump-ctx" in argv
    seconds = 1200
    target = "<WXID_FRIEND_A>"
    tpl = 0
    # 捕获后按这些延迟（秒）各发一次，用来测「任务上下文的复用时效」
    schedule = [5, 60, 300]
    # 自动触发的命令类型：8 = 收藏表情，12 = 表情包（表情商店）表情
    cmd_type = 8
    for i, a in enumerate(argv):
        if a == "--seconds" and i + 1 < len(argv):
            seconds = int(argv[i + 1])
        elif a == "--target" and i + 1 < len(argv):
            target = argv[i + 1]
        elif a == "--tpl" and i + 1 < len(argv):
            tpl = int(argv[i + 1])
        elif a == "--cmd-type" and i + 1 < len(argv):
            cmd_type = int(argv[i + 1])
        elif a == "--schedule" and i + 1 < len(argv):
            schedule = [int(x) for x in argv[i + 1].split(",") if x.strip()]

    REPORTS.mkdir(parents=True, exist_ok=True)
    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name.lower() == "weixin.exe"]
    if not procs:
        print("Weixin.exe 未运行")
        return 1

    print(f"自动触发发送: {autosend} | 目标 {target} | type=8 模板 {tpl}")

    sessions = []
    state = {"captured": False, "sent_seq": None, "injected": False}

    for p in procs:
        out = REPORTS / f"frida_ctx_{p.pid}.txt"
        out.write_text("", encoding="utf-8")

        def make_handler(cur_pid):
            def handler(message, data):  # noqa: ANN001, ARG001
                if message.get("type") == "error":
                    print(f"  [pid={cur_pid}] script error:", message.get("description"))
                    return
                if message.get("type") != "send":
                    return
                payload = message.get("payload") or {}
                ev = payload.get("ev")
                if ev == "captured":
                    print(f"  [pid={cur_pid}] CAPTURED body={payload.get('body')} "
                          f"ctrl={payload.get('ctrl')}")
                    if not state["captured"]:
                        state["captured"] = True
                        state["pid"] = cur_pid
                    # 落盘给 DLL 用：DLL 的 send_sticker_pack 会读这个文件填 d4
                    if dump_ctx:
                        try:
                            ctx_file = CONTROL / "ctx_override.txt"
                            # 必须去掉 0x 前缀：DLL 侧的 strtoull_hex 遇到 'x'
                            # 会中止解析并得到 0（本次踩过）。
                            body_hex = str(payload.get("body", "")).replace("0x", "")
                            ctrl_hex = str(payload.get("ctrl", "")).replace("0x", "")
                            ctx_file.write_text(
                                f"BODY={body_hex}\n"
                                f"CTRL={ctrl_hex}\n"
                                f"PID={cur_pid}\n",
                                encoding="utf-8")
                            print(f"  [pid={cur_pid}] 已落盘 {ctx_file} "
                                  f"(BODY={body_hex} CTRL={ctrl_hex})")
                        except Exception as ex:  # noqa: BLE001
                            print(f"  [pid={cur_pid}] 落盘失败: {ex}")
                elif ev == "content":
                    slots = payload.get("slots") or {}
                    print(f"  [pid={cur_pid}] CONTENT carrier={slots.get('slot0')} "
                          f"slot2={slots.get('slot2')} slot8={slots.get('slot8')}")
                    # 自动采集：把发过的表情攒成模板表，便于后续 DLL 直接调用
                    try:
                        tpl_file = REPORTS / "collected_templates.json"
                        collected = []
                        if tpl_file.exists():
                            collected = json.loads(
                                tpl_file.read_text(encoding="utf-8") or "[]")
                        entry = {
                            "lib_md5": slots.get("slot0", ""),
                            "spec_md5": slots.get("slot2", ""),
                            "aux_md5": slots.get("slot8", ""),
                            "url_20401": slots.get("slot6", ""),
                            "url_20403": slots.get("slot7", ""),
                            "url_20402": slots.get("slot9", ""),
                            # 原始 12 槽全量留档：表情包/商店表情的字段位置与收藏表情
                            # 不同（实测只有 slot0 有值），必须留原始数据才能后续解析
                            "raw_slots": slots,
                        }
                        if not entry["lib_md5"]:
                            print(f"  [pid={cur_pid}] 内容为空，跳过采集")
                        elif any(c.get("lib_md5") == entry["lib_md5"] for c in collected):
                            print(f"  [pid={cur_pid}] 该表情已在模板表内"
                                  f"（共 {len(collected)} 个）")
                        else:
                            collected.append(entry)
                            tpl_file.write_text(
                                json.dumps(collected, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                            print(f"  [pid={cur_pid}] ★ 采集到新模板 "
                                  f"{entry['lib_md5']}（共 {len(collected)} 个）-> {tpl_file.name}")
                    except Exception as ex:  # noqa: BLE001
                        print(f"  [pid={cur_pid}] 模板落盘失败: {ex}")
                elif ev == "injected":
                    print(f"  [pid={cur_pid}] INJECTED d4={payload.get('d4')}")
                    state["injected"] = True
                elif ev == "inject_skip":
                    print(f"  [pid={cur_pid}] INJECT SKIPPED: {payload.get('reason')}")
            return handler

        try:
            session = frida.attach(p.pid)
            script = session.create_script(build_js(out, autosend))
            script.on("message", make_handler(p.pid))
            script.load()
            sessions.append((p.pid, session, script, out))
            print(f"  已挂 pid={p.pid} -> {out.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  pid={p.pid} attach 失败: {e}")

    if not sessions:
        print("没有进程挂载成功")
        return 1

    print("\n>>> 第一步：请在微信里手动发一个收藏表情（任意，发给谁都行）——用于捕获真实上下文")
    print(f">>> 捕获后将在 t+{schedule} 秒各发一次（复用同一个上下文），用来测复用时效")

    deadline = time.time() + seconds
    last = {pid: 0 for pid, _, _, _ in sessions}
    capture_at = None
    fired = set()
    seqs = []
    while time.time() < deadline:
        time.sleep(1.0)
        for pid, _, _, out in sessions:
            try:
                n = len(out.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                n = 0
            if n != last[pid]:
                last[pid] = n

        if state["captured"] and capture_at is None:
            capture_at = time.time()
            print("\n>>> 已捕获真实上下文（t=0），开始时效测试")

        if autosend and capture_at is not None:
            for delay in schedule:
                if delay in fired or time.time() - capture_at < delay:
                    continue
                fired.add(delay)
                seq = str(int(time.time() * 1000))
                try:
                    write_outbox(seq, target, tpl, cmd_type)
                    seqs.append((delay, seq))
                    print(f">>> t+{delay}s 写 outbox: type={cmd_type} tpl={tpl} -> {target} (seq={seq})")
                except Exception as e:  # noqa: BLE001
                    print(f">>> t+{delay}s 写 outbox 失败: {e}")
            if len(fired) >= len(schedule) and time.time() - capture_at > max(schedule) + 25:
                print("\n>>> 时效测试完成")
                break

    for pid, session, script, _ in sessions:
        try:
            script.unload()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass

    print("\n== 结果 ==")
    for pid, _, _, out in sessions:
        txt = ""
        try:
            txt = out.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        if txt.strip():
            print(f"--- {out.name} ---")
            print(txt.strip())
    if seqs:
        print("\n--- DLL 结果（按注入时刻） ---")
        for delay, seq in seqs:
            print(f"t+{delay}s (seq={seq}): {read_result(seq)}")
        st = CONTROL / "status.txt"
        if st.exists():
            print("status.txt:", st.read_text(encoding="utf-8", errors="replace").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
