"""载体替换（carrier swap）—— 让一次真实点击发出任意收藏表情。

原理
----
前 25 节的失败路线是「手工拼装信封 + 任务上下文」，第 20.5 节已证明发送任务
上下文（0xDB40 第 5 参数）无法伪造；第 24 节证明即使信封/内容对象与原生逐字段
一致，入队之后仍被判失败。

本脚本换一条路：**一个字节的对象都不构造**。让用户自然发送任意一个收藏表情
（"载体"），在 pack 提交点 0x160EBE0 的入口处，把这个消息的内容对象里的 6 个
std::string 槽就地覆写成目标表情的 md5 / CDN URL。任务上下文、信封、委托、
队列、序列化——全部由微信自己产生，我们只改 6 个字符串。

为什么安全
----------
内容对象布局（实测，见 reports/frida_cfg.txt 第 434-441 行）：
  信封 vtable          0x82CB8D8
  信封 +0x660          内容对象（对象体指针，裸指针）
  内容对象 +0x00       对象体 vtable = 0x8755528
  内容对象 +0x10+k*0x20 第 k 个 std::string（buf16 / len@+0x10 / cap@+0x18）

  槽位   偏移      字段        实测 len / cap
  slot0  +0x010   lib_md5      32  / 0x2f = 47
  slot2  +0x050   spec_md5     32  / 0x2f
  slot6  +0x090   url 20401   324  / 0x14f = 335
  slot7  +0x0b0   url 20403   322  / 0x14f
  slot8  +0x0d0   aux_md5      32  / 0x2f
  slot9  +0x0f0   url 20402   324  / 0x14f

所有表情的槽位长度都是定长（md5 恒 32；URL 恒 324/322，因为 filekey 内嵌 md5
与 storeid 均为定长），因此 cap 永远够用：就地覆写不会触发任何重新分配，
不会调用 operator new，不会释放任何缓冲。

用法
----
    python frida_sticker_swap.py                       # dry-run，只观察
    python frida_sticker_swap.py --live --target 0     # 真正替换成模板 0
    python frida_sticker_swap.py --live --target 0 --pid 33548

输出
----
    reports/frida_swap_<pid>.txt
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import frida

REPORTS = Path(r"<PROJECT_ROOT>\reports")

# 7 个模板，取自 src/include/wx_sticker_templates.h（源: reports/sticker_templates.json）
# 字段顺序与结构体 wxb_stk_tpl 一致。
TEMPLATES = [
    {
        "lib_md5": "0fbdd73cc59f210845f4d2457b0167b8",
        "spec_md5": "9558c0a6b75d4821b7b68c2eecb19eac",
        "aux_md5": "8cbd585dba8bb6cc4d5c0a7ccfead51d",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=0fbdd73cc59f210845f4d2457b0167b8&filekey=30440201010430302e02016e0402534804203066626464373363633539663231303834356634643234353762303136376238020301be53040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000c1301e36a4af20000006e01004fb15348025e866150411ac27&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=3e5a0552c232deabe5a0d4e8a6aa0422&filekey=3043020101042f302d02016e0402534804203365356130353532633233326465616265356130643465386136616130343232020226a0040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000e423ee36a4af20000006e03004fb35348025e866150411ac48&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=1e0ce94dc8da48370f4614709973271c&filekey=30440201010430302e02016e0402534804203165306365393464633864613438333730663436313437303939373332373163020301be60040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000d205ae36a4af20000006e02004fb25348025e866150411ac37&ef=2&bizid=1022",
    },
    {
        "lib_md5": "53dcede756bc62e5e7cfb3eca4c3b5c5",
        "spec_md5": "47a7ee64be7f48bea221fff11c1afcef",
        "aux_md5": "d85a76430c0abecd1715fc0b723b0e20",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=53dcede756bc62e5e7cfb3eca4c3b5c5&filekey=30440201010430302e02016e0402534804203533646365646537353662633632653565376366623365636134633362356335020302209b040d00000004627466730000000132&hy=SH&storeid=26a5d7a9f000e4eb7e36a4af20000006e01004fb153480fd3b03157b5d6feb&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=f0b6c132c1bf914a6b3988e987f975b2&filekey=3043020101042f302d02016e040253480420663062366331333263316266393134613662333938386539383766393735623202023250040d00000004627466730000000132&hy=SH&storeid=26a5d7aa00000d4a5e36a4af20000006e03004fb353480fd3b03157b5d700a&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=7430d39e838150c21e91969c2b1e0cc7&filekey=30440201010430302e02016e040253480420373433306433396538333831353063323165393139363963326231653063633702030220a0040d00000004627466730000000132&hy=SH&storeid=26a5d7aa000000412e36a4af20000006e02004fb253480fd3b03157b5d6ff8&ef=2&bizid=1022",
    },
    {
        "lib_md5": "7ed206382321db118c4951f1e448166a",
        "spec_md5": "49cd60dd1f354795b1334bf655a189a5",
        "aux_md5": "96d1ce52eeffc92219b7524763fbf5d5",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=7ed206382321db118c4951f1e448166a&filekey=30440201010430302e02016e04025348042037656432303633383233323164623131386334393531663165343438313636610203021390040d00000004627466730000000132&hy=SH&storeid=26a5d7ba3000639e9e36a4af20000006e01004fb1534807e3c03157101db45&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=5f3c31ac7ae8771f51519ce40409ed7a&filekey=3043020101042f302d02016e0402534804203566336333316163376165383737316635313531396365343034303965643761020230d0040d00000004627466730000000132&hy=SH&storeid=26a5d7ba30007b824e36a4af20000006e03004fb3534807e3c03157101db5d&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=455d847059730c65bff4e247110bfd03&filekey=30440201010430302e02016e040253480420343535643834373035393733306336356266663465323437313130626664303302030213a0040d00000004627466730000000132&hy=SH&storeid=26a5d7ba300070b2ce36a4af2000006e02004fb2534807e3c03157101db4e&ef=2&bizid=1022",
    },
    {
        "lib_md5": "b90ff3bbdb9eb50b8324bb7d6631a3ef",
        "spec_md5": "957d07571c034bba8d2ecfec7266f181",
        "aux_md5": "245b5f04c2d19a6ea5cc7a63bb978aae",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=b90ff3bbdb9eb50b8324bb7d6631a3ef&filekey=30440201010430302e02016e0402534804206239306666336262646239656235306238333234626237643636333161336566020301eb95040d00000004627466730000000132&hy=SH&storeid=26a5d7be5000da3bbe36a4af20000006e01004fb1534819ec117156cb3474c&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=8dbf645611ebb473c7c56f417e421d49&filekey=3043020101042f302d02016e040253480420386462663634353631316562623437336337633536663431376534323164343902022600040d00000004627466730000000132&hy=SH&storeid=26a5d7be6000033a6e36a4af20000006e03004fb3534819ec117156cb34781&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=e61d9ddc83e7d47b2fc51014dc9f1475&filekey=30440201010430302e02016e0402534804206536316439646463383365376434376232666335313031346463396631343735020301eba0040d00000004627466730000000132&hy=SH&storeid=26a5d7be5000eb0d2e36a4af20000006e02004fb2534819ec117156cb3476a&ef=2&bizid=1022",
    },
    {
        "lib_md5": "cbab1418a65ab56a82b228ea2a27c621",
        "spec_md5": "7901cc692c1442f49374e9f9722e44d8",
        "aux_md5": "c69a8064b008420fdc9cfbaca518df7a",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=cbab1418a65ab56a82b228ea2a27c621&filekey=30440201010430302e02016e0402534804206362616231343138613635616235366138326232323865613261323763363231020301bd8f040d00000004627466730000000132&hy=SH&storeid=26a5d7bd4000eef3fe36a4af20000006e01004fb153481c6e9661502d4eb91&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=1d6df9a373105c40206f31512982f91c&filekey=3043020101042f302d02016e040253480420316436646639613337333130356334303230366633313531323938326639316302022320040d00000004627466730000000132&hy=SH&storeid=26a5d7bd50001aa6ee36a4af20000006e03004fb353481c6e9661502d4ebb3&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=b4ede003a7df784d24142eb451ef2f66&filekey=30440201010430302e02016e0402534804206234656465303033613764663738346432343134326562343531656632663636020301bd90040d00000004627466730000000132&hy=SH&storeid=26a5d7bd50000bc9ce36a4af2000006e02004fb253481c6e9661502d4eba2&ef=2&bizid=1022",
    },
    {
        "lib_md5": "ccfabb49a1904b17159ba9f6bb9b3782",
        "spec_md5": "1402a1e027bd42e885ecc990381318e0",
        "aux_md5": "203cb0736f7a726941e01062a3d38431",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=ccfabb49a1904b17159ba9f6bb9b3782&filekey=30440201010430302e02016e04025348042063636661626234396131393034623137313539626139663662623962333738320203022bad040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000bd4b5e36a4af20000006e01004fb153482cf3c1f1502cab27d&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=3f2307c65a07d7373125a2c7a56b2a01&filekey=3043020101042f302d02016e040253480420336632333037633635613037643733373331323561326337613536623261303102023260040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000d9589e36a4af20000006e03004fb353482cf3c1f1502cab293&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=d1cc6393f7fb0693c317b7624021e58f&filekey=30440201010430302e02016e04025348042064316363363339336637666230363933633331376237363234303231653538660203022bb0040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000cbdd9e36a4af20000006e02004fb253482cf3c1f1502cab28a&ef=2&bizid=1022",
    },
    {
        "lib_md5": "d727ccdf2475c436206cbc8ec3fa30b9",
        "spec_md5": "cd784b225d1948b986dca2d013196923",
        "aux_md5": "63d09b6fac72997727e5430db24f8f92",
        "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=d727ccdf2475c436206cbc8ec3fa30b9&filekey=30440201010430302e02016e04025348042064373237636364663234373563343336323036636263386563336661333062390203020db6040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000aa62fe36a4af20000006e01004fb153482ab3f031502cd1c51&ef=1&bizid=1022",
        "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=0fb3fed79b06e10dfcb1cd95355fafcb&filekey=3043020101042f302d02016e040253480420306662336665643739623036653130646663623163643935333535666166636202022fc0040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000c9d47e36a4af20000006e03004fb353482ab3f031502cd1c70&ef=3&bizid=1022",
        "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=8724a7bc86b8cb42b08834f4168c3399&filekey=30440201010430302e02016e04025348042038373234613762633836623863623432623038383334663431363863333339390203020dc0040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000b9113e36a4af20000006e02004fb253482ab3f031502cd1c60&ef=2&bizid=1022",
    },
]

# 信封 vtable（收藏表情）与内容对象对象体 vtable，均为实测值
VT_STICKER_ENVELOPE = "0x82cb8d8"
VT_CONTENT_BODY = "0x8755528"

JS_TEMPLATE = r"""
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = __OUT__;
const TEMPLATES = __TEMPLATES__;
const TARGET_IDX = __TARGET__;
const LIVE = __LIVE__;
const MAX_SWAPS = __MAX_SWAPS__;

const VT_ENV = "__VT_ENV__";
const VT_BODY = "__VT_BODY__";

// 槽位 -> 模板字段
const SLOT_MAP = {
    0: "lib_md5",
    2: "spec_md5",
    6: "url_20401",
    7: "url_20403",
    8: "aux_md5",
    9: "url_20402"
};

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

function hexOf(p, n) {
    try {
        return Array.from(new Uint8Array(p.readByteArray(n)))
            .map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    } catch (e) { return "ERR " + e; }
}

function slotOff(slot) {
    // 内容对象对象体的第 slot 个字符串：buf @ +0x10+slot*0x20
    return 0x10 + slot * 0x20;
}

function readSlot(obj, slot) {
    const off = slotOff(slot);
    let len = 0, cap = 0, txt = "";
    try {
        len = obj.add(off + 0x10).readInt();
        cap = obj.add(off + 0x18).readInt();
        if (len > 0 && len < 8192) {
            let buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
            if (!buf.isNull()) txt = buf.readUtf8String(len);
        }
    } catch (e) {
        txt = "<ERR " + e + ">";
    }
    return { len: len, cap: cap, txt: txt };
}

function writeSlot(obj, slot, text) {
    const off = slotOff(slot);
    let cap = 0;
    try { cap = obj.add(off + 0x18).readInt(); } catch (e) { return "CAP_ERR"; }
    // 硬安全阀：只在原容量内就地覆写，绝不重新分配
    if (text.length > cap) return "NO_ROOM(len=" + text.length + " cap=" + cap + ")";
    let buf = null;
    try {
        buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
    } catch (e) { return "BUF_ERR"; }
    if (buf === null || buf.isNull()) return "NULL_BUF";
    try {
        buf.writeUtf8String(text);
        buf.add(text.length).writeU8(0);          // std::string 要求 buf[len] = 0
        obj.add(off + 0x10).writeInt(text.length);
    } catch (e) { return "WRITE_ERR " + e; }
    return "OK";
}

w("== sticker swap loaded base=" + base.toString() + " live=" + LIVE +
  " target=" + TARGET_IDX + " ==");

let swaps = 0;

Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        const tid = Process.getCurrentThreadId();
        try {
            const b = args[0].add(8).readPointer();
            const e = args[0].add(0x10).readPointer();
            const n = e.sub(b).toInt32() / 16;
            if (n <= 0 || n > 32) return;              // 不是我们关心的提交
            let s = "PACK tid=" + tid + " models=" + n + "\n";
            for (let i = 0; i < Math.min(n, 4); i++) {
                let m = null, vt = "?";
                try {
                    m = b.add(i * 16).readPointer();
                    vt = rva(m.readPointer());
                } catch (e1) { s += "  model" + i + " read ERR\n"; continue; }
                s += "  model" + i + " vt=" + vt + "\n";
                if (vt !== VT_ENV) continue;           // 只处理收藏表情信封

                let cb = null, cvt = "?";
                try {
                    cb = m.add(0x660).readPointer();
                    if (cb.isNull()) { s += "    +0x660 NULL\n"; continue; }
                    cvt = rva(cb.readPointer());
                } catch (e2) { s += "    content read ERR\n"; continue; }
                s += "    content=" + cb + " vt=" + cvt + "\n";
                if (cvt !== VT_BODY) continue;         // 布局不符则不碰

                const before = {};
                Object.keys(SLOT_MAP).forEach(function (k) {
                    before[k] = readSlot(cb, parseInt(k, 10));
                    s += "      before slot" + k + " " + SLOT_MAP[k] +
                         " len=" + before[k].len + " cap=" + before[k].cap +
                         " : " + before[k].txt + "\n";
                });

                // 载体 == 目标时自动换一个，保证一次点击就能看出差异
                let ti = TARGET_IDX;
                if (ti < 0 || ti >= TEMPLATES.length) ti = 0;
                if (before[0].txt === TEMPLATES[ti].lib_md5) {
                    ti = (ti + 1) % TEMPLATES.length;
                }
                s += "      carrier=" + before[0].txt +
                     "  ->  target[" + ti + "]=" + TEMPLATES[ti].lib_md5 + "\n";

                if (!LIVE) {
                    // 完整对象体 hex：万一槽位映射有偏差，事后可离线重新解析
                    s += "      body_hex=" + hexOf(cb, 0x1B0) + "\n";
                    s += "      DRY-RUN：只观察，未写入\n";
                    w(s);
                    send({ hit: "dryrun", content: cb.toString(),
                           carrier: before[0].txt });
                    continue;
                }
                if (swaps >= MAX_SWAPS) {
                    s += "      已达写入上限 " + MAX_SWAPS + "，跳过\n";
                    w(s);
                    continue;
                }

                let allOk = true;
                Object.keys(SLOT_MAP).forEach(function (k) {
                    const r = writeSlot(cb, parseInt(k, 10), TEMPLATES[ti][SLOT_MAP[k]]);
                    s += "      write slot" + k + " " + SLOT_MAP[k] + " -> " + r + "\n";
                    if (r !== "OK") allOk = false;
                });
                Object.keys(SLOT_MAP).forEach(function (k) {
                    const a = readSlot(cb, parseInt(k, 10));
                    s += "      after  slot" + k + " len=" + a.len + " : " +
                         a.txt.substring(0, 72) +
                         (a.txt.length > 72 ? "…" : "") + "\n";
                });
                if (allOk) {
                    swaps++;
                    s += "      SWAP#" + swaps + " 完成\n";
                    send({ hit: "swapped", target: TEMPLATES[ti].lib_md5 });
                }
                w(s);
            }
            if (n > 0 && s.indexOf("model0 vt=" + VT_ENV) < 0) w(s);
        } catch (err) {
            w("PACK ERR " + err);
        }
    }
});

w("attached pack 0x160EBE0");
"""


def build_js(out_path: Path, target: int, live: bool, max_swaps: int) -> str:
    js = JS_TEMPLATE
    js = js.replace("__OUT__", json.dumps(str(out_path)))
    js = js.replace("__TEMPLATES__", json.dumps(TEMPLATES, ensure_ascii=False))
    js = js.replace("__TARGET__", str(target))
    js = js.replace("__LIVE__", "true" if live else "false")
    js = js.replace("__MAX_SWAPS__", str(max_swaps))
    js = js.replace("__VT_ENV__", VT_STICKER_ENVELOPE)
    js = js.replace("__VT_BODY__", VT_CONTENT_BODY)
    return js


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    argv = sys.argv[1:]
    live = "--live" in argv
    target = 0
    seconds = 180
    pid_filter = None
    max_swaps = 1
    for i, a in enumerate(argv):
        if a == "--target" and i + 1 < len(argv):
            target = int(argv[i + 1])
        elif a == "--seconds" and i + 1 < len(argv):
            seconds = int(argv[i + 1])
        elif a == "--pid" and i + 1 < len(argv):
            pid_filter = int(argv[i + 1])
        elif a == "--max-swaps" and i + 1 < len(argv):
            max_swaps = int(argv[i + 1])
        elif a.isdigit():
            seconds = int(a)

    REPORTS.mkdir(parents=True, exist_ok=True)
    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name.lower() == "weixin.exe"]
    if pid_filter is not None:
        procs = [p for p in procs if p.pid == pid_filter]
    if not procs:
        print("Weixin.exe 未运行（或 --pid 不匹配）")
        return 1

    mode = "LIVE 写入" if live else "DRY-RUN 只观察"
    print(f"模式: {mode} | 目标模板 {target} = {TEMPLATES[target]['lib_md5'] if 0 <= target < len(TEMPLATES) else '?'}")
    print(f"候选进程: {[p.pid for p in procs]}")

    sessions = []
    hits = set()
    for p in procs:
        out = REPORTS / f"frida_swap_{p.pid}.txt"
        out.write_text("", encoding="utf-8")

        def make_handler(cur_pid):
            def handler(message, data):  # noqa: ANN001, ARG001
                if message.get("type") == "error":
                    print(f"  [pid={cur_pid}] script error:", message.get("description"))
                elif message.get("type") == "send":
                    payload = message.get("payload") or {}
                    if isinstance(payload, dict) and payload.get("hit"):
                        print(f"  [pid={cur_pid}] HIT {payload}")
                        hits.add(cur_pid)
            return handler

        try:
            session = frida.attach(p.pid)
            script = session.create_script(build_js(out, target, live, max_swaps))
            script.on("message", make_handler(p.pid))
            script.load()
            sessions.append((p.pid, session, script, out))
            print(f"  已挂 pid={p.pid} -> {out.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  pid={p.pid} attach 失败: {e}")

    if not sessions:
        print("没有任何进程挂载成功")
        return 1

    print(f"\n>>> 现在请在微信里手动发送一个收藏表情（发给任意会话，建议发给自己/文件传输助手）。")
    print(f">>> 观察 {seconds} 秒……\n")

    deadline = time.time() + seconds
    last = {pid: 0 for pid, _, _, _ in sessions}
    while time.time() < deadline:
        time.sleep(2.0)
        for pid, _, _, out in sessions:
            try:
                n = len(out.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                n = 0
            if n != last[pid]:
                print(f"  pid={pid} lines={n}")
                last[pid] = n
        if hits and not live:
            print(f"  已捕获内容对象 (pid={sorted(hits)})，结束观察")
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
        try:
            txt = out.read_text(encoding="utf-8", errors="replace")
        except Exception:
            txt = ""
        print(f"--- {out} ({len(txt.splitlines())} 行) ---")
        print(txt.strip() or "(无输出：该进程未发生 pack 提交)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
