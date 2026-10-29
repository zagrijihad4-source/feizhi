# -*- coding: utf-8 -*-
"""绯栀的语音发送（微信语音消息）。

链路：文本 --(MiMo TTS，克隆音色 + 情绪指令)--> wav --> 16k PCM
      --(frida 注入 SILK 编码器)--> 微信自己编码/上传/发送

关键实现（都是 2026-10-15 实测确立的）：

1. **注入点**：`VoipEngine.dll!SKP_Silk_SDK_Encode` 的第 3 个参数是 PCM 输入，
   每帧 320 samples @16000Hz 单声道。覆写它，其余全交给微信。

2. **免前台**：微信的「按住右 Alt 说话」原本要窗口焦点。改为
   `keybd_event` 让系统键盘状态里 Alt 真按下（微信会校验，只发消息的话
   录音只能撑 0.24 秒）+ `PostMessage(WM_KEYDOWN)` 单独投递给微信窗口。
   实测全程不抢用户前台。必须用 WM_KEYDOWN，WM_SYSKEYDOWN 无效。

3. **frida 常驻**：attach 一次反复使用。批量发送时不能用 recv/post 传数据
   （frida 的 recv 处理器触发一次后失效），要用 rpc + File.readAllBytes 读 PCM 文件。

局限：语音发到微信**当前打开的聊天窗口**。如果用户手动切到了别的会话，
这条语音会发到那里——自动回复场景下需要自行确认窗口停在目标会话。
"""
from __future__ import annotations

import ctypes
import logging
import random
import threading
import time
from ctypes import wintypes
from pathlib import Path

import frida

from tts import synthesize_pcm, TTSError

LOG = logging.getLogger("feizhi_pc.voice")

SR = 16000          # 微信 SILK 编码器的采样率
FRAME = 320         # 每帧样本数（20ms）

# ---------------------------------------------------------------- 情绪档位
# LLM 只写档位名，这里给出对应的导演指令（MiMo 的自然语言风格控制）。
# 写法参考实测有效的模式：角色 / 场景 / 指导三段，指导落到气息、语速、重音。
# ★ 指导里**不许出现「停顿 / 顿一下」**：MiMo 对它是反向响应，一提就狂插静音
#   （见下方 RHYTHM 那段血泪教训）。2026-10-27 复查发现「委屈」「强撑」两档
#   原本各写了一句「留一点停顿」，已改成偏慢/接紧这类正面措辞。
MOODS: dict[str, dict[str, str]] = {
    "傲娇": {
        "desc": "嘴硬心软：先冷淡，后半句藏不住在乎",
        "style": (
            "像嘴上还在恼他、心里其实已经软了：开口先冷一句，声音压着、字咬得实；"
            "说到一半自己绷不住，气音里漏出一点笑意；最后那句小声嘟囔，尾音往下掉。"
            "前面硬，后面软，别一路都硬。"
        ),
    },
    "心虚": {
        "desc": "被说中，慌着否认",
        "style": (
            "像被他一句话说中心事、慌忙否认：开口先卡了一下，语速变快；"
            "越否认越没底气，音量一路收小、气息变浅；最后几乎是在嘟囔，尾音散掉。"
            "前面冲，后面虚，中间那一下要听得出来。"
        ),
    },
    "委屈": {
        "desc": "被冷落，有点赌气又不肯说重",
        "style": (
            "像等了很久又不想显得太在意：开头声音低、故意放平；"
            "说到一半没忍住带了鼻音，句子断了一下又接上；最后一句轻轻收，尾音往下坠。"
            "前面平，后面散，中间要听得出忍住的那一下。"
        ),
    },
    "温柔": {
        "desc": "声音软下来，不刺人",
        "style": (
            "把声音放软：开口轻、气息暖，语速比平时慢半拍但不拖，"
            "尾音收得柔，带一点笑意。"
            "软而不冷、软而不腻 —— 不要压低音量装温柔，也不要拖着调子撒娇，"
            "就是自然地放轻，整段是松的，不是虚的。"
        ),
    },
    # 2026-10-29 按用户挑样本加的：同一句话三个变体里他选了这个
    # （另两个是「带笑出声」和原温柔档）。特点是不装温柔也不端着，
    # 声音往上走、有精神，但**不靠提高音调**——升调会把音色整个换掉。
    "明快": {
        "desc": "心情好，说话带笑",
        "style": (
            "说话轻快明亮，语速比平时快一点，尾音带一点笑意；"
            "整段是往上走的、有精神的，像刚碰上件好事还没说完。"
            "别硬装开心，也别拔高音调 —— 高兴是语速和语气的事。"
        ),
    },
    "慵懒": {
        "desc": "刚醒 / 深夜，字都黏在一起",
        "style": (
            "像刚被消息吵醒、人还没清醒：开口含混，字黏在一起；"
            "中间懒懒地拖长应了一声；最后音量低下去，像又要睡过去。"
            "整段是松的，不是慢的。"
        ),
    },
    "开心": {
        "desc": "忘了维持形象",
        "style": (
            "像突然收到好消息：开口语速就快起来，字咬得轻快、不拖；"
            "中间笑出来，笑完接着说；最后一句干脆收住。"
            "高兴靠语速和笑，不靠提高音调。"
        ),
    },
    "强撑": {
        "desc": "自己难受但硬说没事",
        "style": (
            "像自己其实很难受、但他一问就硬撑说没事：开口刻意保持平稳，太稳了点；"
            "中间气息短了一下、露出破口；最后那句「没事」说得又快又轻。"
            "越稳越假，那个破口一定要有。"
        ),
    },
    "娇嗔": {
        "desc": "撒娇，带点耍赖",
        "style": (
            "像跟他耍赖要东西：话说得比平时黏一点、带鼻音；"
            "中间夹一声没忍住的轻笑；最后一句说得**短**、带点不服气地收住。"
            "娇是不讲理，不是拖音 —— 整句不要拖长，拖长了就变成懒。"
        ),
    },
    # 2026-10-27 新增：模型写过 `[voice:害羞:...]`，但档位表里没有这个键，
    # 于是静默回退到「傲娇」——文本是「宝宝我好喜欢你啦」这种害羞的情话，
    # 声音却是「前半句冷淡、笑到一半收住」，内容和语气互相抵消。
    # 这类高频情绪必须显式给一档，别再让它掉进兜底。
    "害羞": {
        "desc": "被说得心里发热，声音变小",
        "style": (
            "像被说得心里发热、但没躲开：开口迟疑了半秒，声音变小；"
            "说到一半忍不住笑了，笑意压在声音里；最后一句轻轻收，尾音软。"
            "音量小，但要暖，别冷。"
        ),
    },
}

# 档位兜底：未知 mood 一律回退到这一档。
# ★ 不能回退到「傲娇」—— 傲娇档的导演指令是「前半句冷淡、笑到一半收住」，
#   拿它去念情话，声音和内容会打架（2026-10-27 实测）。
FALLBACK_MOOD = "温柔"

DEFAULT_MOOD = "明快"      # 2026-10-29 用户挑样本后定的默认调子

# 统一节奏约束（★ 必须有）。
# 实测：只给情绪不给节奏时，MiMo 会为了表现「冷淡 / 赌气 / 笑到一半收住」而插入
# 大量停顿 —— 「就你？赢谁了，人机吗。」这 12 个字被拖成 9.12 秒，其中 4.99 秒是静音
# （8 段，每段 0.5~0.85 秒）。加上这条之后时长回到正常口语区间。
# ---------------------------------------------------------------- 节奏控制
# ★★ 血泪教训：**绝对不要在给 MiMo 的指令里出现「停顿 / 顿一下」这类词。**
#    它是反向响应，一提就疯狂插静音。同一句 22 字「你快点回我啊，我等半天了，
#    手机都快看没电了。」的 A/B 实测：
#        只有导演指令（无任何节奏描述）   5.60s   3.93 字/秒
#        + 「语速偏快」                  5.28s   4.17 字/秒   ← 最快，用这个
#        + 「又急又快，像急着把话说完」    6.08s   3.62 字/秒
#        + 含停顿描述的 RHYTHM          20.16s   1.09 字/秒   ← 灾难
#    所以这里只用**正向、简短、不含停顿语义**的措辞。
RHYTHM = "语速自然偏快，连贯地说完。"

# 各档位特有的快慢处理（同样只用正向措辞）。"慢"本身无害，
# 「停顿」才致命 —— 慵懒/委屈档一直偏慢，但从未出现 20 秒这种灾难。
MOOD_RHYTHM: dict[str, str] = {
    "傲娇": "语气干脆，语速偏快。",
    "心虚": "语速偏快，声音发虚。",
    "委屈": "语速慢一些，尾音往下坠。",
    "温柔": "语速平缓，轻声。",
    "慵懒": "语速慢，字与字黏在一起，尾音拖长。",
    "开心": "语速快，一句接一句。",
    "强撑": "语速平快，像排练过的。",
    "娇嗔": "前面说得快，后面拖长音。",
    "害羞": "声音小一点，语速慢一点，尾音软。",
}


def style_for(mood: str) -> str:
    """拼出该档位的完整风格指令。

    ★ 按 provider 走两条路（2026-10-27）：
      * **breeze**：只返回 mood 的 style 本身。它已经是「情境开场 + 段内两到三拍变化」
        的写法，速度交给 `voice_settings.speed`（它是保持音高的整体变速，比文字描述精确）。
        再拼 RHYTHM / MOOD_RHYTHM 会稀释重点——实测拼了之后 F0 起伏反而降。
      * **mimo**：沿用 三段式 + 该档语速 + 整体语速 的老写法（那套是为 chat 端点的
        style 参数调的，注释里的血泪教训都在）。
    """
    entry = MOODS.get(mood) or MOODS[FALLBACK_MOOD]
    breeze = False
    try:
        import tts as _tts
        breeze = str(_tts.load_config().get("provider") or "").lower() == "breeze"
    except Exception:  # noqa: BLE001
        breeze = False
    if breeze:
        # ★ 音高约束必须统一兜底（2026-10-27 血的教训）：
        #   各档配方里出现过「声音往上扬 / 音调偏高 / 拔高 / 往上飘」这类描述，
        #   模型把整体调门抬上去，同一音色 F0 均值从 205 跑到 473（+130%），
        #   声线直接换了个人 —— 用户的原话是「音色都体现不出来了」。
        #   情绪要靠语速、音量、气息、停顿来表达，不是靠升调。
        #
        # ★ 2026-10-28 追加：**配方里的情境只是语气示例，不是这一轮的剧情**。
        #   实测翻车：温柔档第一句写的是「像他说了句『我好累』」，而<OWNER>实际说的是
        #   「想听你说话了」，模型照配方演成"哄一个累坏的人"，软塌塌又像在可怜他 ——
        #   用户的原话是「音色不对，语气也不太对」。九个档位都有这种绑定，
        #   这一句统一把它们拉回来。
        return entry["style"] + (
            "\n★ 上面写的是**语气怎么走**，不是这段对话的剧情。"
            "描述里提到的情境（他累了、他夸你、他惹你）只是拿来举例的，"
            "真正的场面由这段聊天决定：他说「想听你说话」就按这个来，"
            "别套成他累了要你哄。\n"
            "音高保持平时说话的调门，不要提高声调，也不要假声或气声拉高。"
        )
    rhythm = MOOD_RHYTHM.get(mood) or MOOD_RHYTHM.get(FALLBACK_MOOD)
    parts = [entry["style"], rhythm, RHYTHM]
    return "\n".join(p for p in parts if p)


def mood_list() -> str:
    return " / ".join(MOODS.keys())


def mood_desc() -> str:
    return "\n".join("  %s：%s" % (k, v["desc"]) for k, v in MOODS.items())


# ---------------------------------------------------------------- frida 脚本
JS = r"""
'use strict';
function exp(n) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(n); } catch (e) {}
    try { return Module.findExportByName(null, n); } catch (e) {}
    return null;
}
var pcmU8 = null, totalSamples = 0, cursor = 0, enabled = false;
var stats = { calls: 0, filled: 0, silent: 0 };
var silence = null;
function ensureSilence(n) {
    if (!silence || silence.length < n * 2) silence = new Uint8Array(Math.max(n, 1024) * 2);
    return silence;
}
var voip = Process.findModuleByName('VoipEngine.dll');
if (!voip) {
    send({ t: 'err', msg: 'VoipEngine.dll 未加载' });
} else {
    var pEnc = voip.findExportByName('SKP_Silk_SDK_Encode');
    Interceptor.attach(pEnc, {
        onEnter: function (a) {
            if (!enabled || !pcmU8) return;
            var n = a[3].toInt32();
            var buf = a[2];
            var avail = totalSamples - cursor;
            stats.calls++;
            if (avail <= 0) {
                buf.writeByteArray(ensureSilence(n).subarray(0, n * 2));
                stats.silent++;
                return;
            }
            var take = n < avail ? n : avail;
            buf.writeByteArray(pcmU8.subarray(cursor * 2, (cursor + take) * 2));
            if (take < n) {
                buf.add(take * 2).writeByteArray(ensureSilence(n - take).subarray(0, (n - take) * 2));
                stats.silent++;
            }
            cursor += take;
            stats.filled++;
        }
    });
    send({ t: 'ok', msg: 'SILK encode hooked' });
}

// ===== 多用户：在 pack 提交点改写语音消息的收件人 =====
// 背景：微信的「按住说话」只会发给**当前打开的会话**，语音走 UI 层、不带 to_wxid
// （文档 A8c）。要做多用户就必须能指定收件人。
//
// 2026-10-28 侦察确认可行：语音消息同样经过 Weixin.dll+0x160EBE0 的 pack 提交，
// 模型 type(+0xD8)=34，vt=0x8b65568，**收件人 wxid 就在 body+0xB0**（std::string），
// 实测 len=19 / cap=31。所有 wxid 都装得下，就地覆写不会触发重新分配 ——
// 和收藏表情的载体替换是同一条路、同一套安全依据（TASK_LOG §26.3）。
//
// 于是流程变成：微信照常录音 -> 编码 -> 上传 -> 构造 voicemsg，
// 我们只在提交前把收件人换掉。不碰 CDN、不点任何东西、不需要目标会话在前台。
var targetWxid = '';

function readStdStr(obj, off) {
    var out = { len: 0, cap: 0, txt: '' };
    try {
        out.len = obj.add(off + 0x10).readInt();
        out.cap = obj.add(off + 0x18).readInt();
        if (out.len > 0 && out.len < 512) {
            var buf = (out.cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
            if (!buf.isNull()) out.txt = buf.readUtf8String(out.len);
        }
    } catch (e) {}
    return out;
}

try {
    var weixin = Process.getModuleByName('Weixin.dll');
    // 微信自己的 operator new —— 扩容 std::string 时必须用它分配。
    // ★ 绝不能用 Memory.alloc：那个缓冲在 frida 的堆上，而微信析构 std::string 时
    //   会走 MSVC 的 delete[]，跨堆释放直接崩进程。用同一个分配器才配对。
    var wxOpNew = null;
    try {
        wxOpNew = new NativeFunction(weixin.base.add(0x64A7D1C), 'pointer', ['size_t']);
    } catch (eOp) {
        send({ t: 'err', msg: 'operator new 解析失败，扩容改写不可用: ' + eOp });
    }
    Interceptor.attach(weixin.base.add(0x160EBE0), {
        onEnter: function (a) {
            if (!targetWxid) return;
            try {
                var b = a[0].add(8).readPointer();
                var e = a[0].add(0x10).readPointer();
                var n = e.sub(b).toInt32() / 16;
                if (n <= 0 || n > 32) return;          // 不是我们关心的提交
                for (var i = 0; i < n; i++) {
                    var m;
                    try { m = b.add(i * 16).readPointer(); } catch (e1) { continue; }
                    var type = -1;
                    try { type = m.add(0xD8).readInt(); } catch (e2) { continue; }
                    if (type !== 34) continue;         // 只动语音，文本/图片/表情一概不碰
                    var recv = readStdStr(m, 0xB0);
                    if (!recv.txt || recv.txt === targetWxid) continue;

                    if (targetWxid.length <= recv.cap && recv.cap > 0xf) {
                        // 堆模式且容量够：就地覆写，最安全
                        var buf = m.add(0xB0).readPointer();
                        if (buf.isNull()) continue;
                        buf.writeUtf8String(targetWxid);
                        buf.add(targetWxid.length).writeU8(0);
                        m.add(0xC0).writeInt(targetWxid.length);
                        send({ t: 'log', m: 'voice retarget: ' + recv.txt +
                              ' -> ' + targetWxid });
                        continue;
                    }

                    if (recv.cap <= 0xf && targetWxid.length <= 0xf) {
                        // SSO 内联且装得下：直接写内联缓冲
                        var sbuf = m.add(0xB0);
                        sbuf.writeUtf8String(targetWxid);
                        sbuf.add(targetWxid.length).writeU8(0);
                        m.add(0xC0).writeInt(targetWxid.length);
                        send({ t: 'log', m: 'voice retarget(SSO): ' + recv.txt +
                              ' -> ' + targetWxid });
                        continue;
                    }

                    // ★ 剩下这一种：原串是 SSO 内联（cap<=15），目标 wxid 更长，装不下。
                    //   实测触发场景：当前会话停在「文件传输助手」（10 字符，内联），
                    //   而目标 wxid 19 字符 —— 改写被跳过，语音就按原样发给了当前会话，
                    //   也就是跑到文件传输助手去了。
                    //   做法：用微信的 operator new 重新分配堆缓冲，把 std::string
                    //   从 SSO 切成堆模式（cap 必须 > 15，析构时它才会 delete[] 这块）。
                    if (!wxOpNew) {
                        send({ t: 'log', m: 'voice retarget SKIP：扩容不可用 cap=' +
                              recv.cap + ' need=' + targetWxid.length });
                        continue;
                    }
                    var need = targetWxid.length + 1;
                    var np = wxOpNew(need);
                    if (np.isNull()) {
                        send({ t: 'log', m: 'voice retarget SKIP：operator new 返回空' });
                        continue;
                    }
                    np.writeUtf8String(targetWxid);
                    np.add(targetWxid.length).writeU8(0);
                    m.add(0xB0).writePointer(np);              // buf 改成堆指针
                    m.add(0xC0).writeInt(targetWxid.length);   // size
                    m.add(0xC8).writeInt(need);                // capacity > 15 => 堆模式
                    send({ t: 'log', m: 'voice retarget(GROW): ' + recv.txt +
                          ' cap' + recv.cap + ' -> ' + targetWxid });
                }
            } catch (err) {
                send({ t: 'log', m: 'voice retarget ERR ' + err });
            }
        }
    });
    send({ t: 'ok', msg: 'pack retarget hooked @0x160EBE0' });
} catch (e) {
    send({ t: 'err', msg: 'pack retarget hook 失败: ' + e });
}
rpc.exports = {
    setTarget: function (wxid) { targetWxid = String(wxid || ''); return targetWxid; },
    clearTarget: function () { targetWxid = ''; return ''; },
    getTarget: function () { return targetWxid; },
    loadfile: function (path) {
        var buf = null;
        try { if (typeof File.readAllBytes === 'function') buf = File.readAllBytes(path); } catch (e) {}
        if (!buf) {
            var f = new File(path, 'rb');
            try {
                if (typeof f.readAllBytes === 'function') buf = f.readAllBytes();
                else if (typeof f.readBytes === 'function') buf = f.readBytes(f.size);
            } finally { try { f.close(); } catch (e) {} }
        }
        if (!buf) throw new Error('无法读取 PCM: ' + path);
        pcmU8 = new Uint8Array(buf);
        totalSamples = (pcmU8.length / 2) | 0;
        cursor = 0;
        return totalSamples;
    },
    arm: function () { cursor = 0; stats = { calls: 0, filled: 0, silent: 0 }; enabled = true; return true; },
    disarm: function () {
        enabled = false;
        return { cursor: cursor, total: totalSamples, calls: stats.calls,
                 filled: stats.filled, silent: stats.silent };
    },
    progress: function () {
        return { cursor: cursor, total: totalSamples, calls: stats.calls,
                 filled: stats.filled, silent: stats.silent };
    }
};
"""

# ---------------------------------------------------------------- Win32
u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.FindWindowW.restype = wintypes.HWND
u32.GetForegroundWindow.restype = wintypes.HWND
u32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_void_p]
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.SetForegroundWindow.restype = wintypes.BOOL
u32.BringWindowToTop.argtypes = [wintypes.HWND]
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetSystemMetrics.argtypes = [ctypes.c_int]
u32.GetSystemMetrics.restype = ctypes.c_int
u32.IsIconic.argtypes = [wintypes.HWND]
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.ShowWindow.restype = wintypes.BOOL
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.GetCurrentThreadId.restype = wintypes.DWORD
u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
u32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
u32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, ctypes.POINTER(wintypes.ULONG)]

MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

VK_RMENU, SCAN_RALT = 0xA5, 0x38
EXT_KEY, KEYUP = 0x0001, 0x0002
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
LP_EXT, LP_CTX, LP_PREV, LP_TRANS = 1 << 24, 1 << 29, 1 << 30, 1 << 31


_inflight = 0
_inflight_lock = threading.Lock()


def _voice_contention() -> bool:
    """现在是不是有多条语音在抢录音通道。"""
    with _inflight_lock:
        return _inflight > 1


def _ralt_lp(down: bool) -> int:
    v = 1 | (SCAN_RALT << 16) | LP_EXT | LP_CTX
    if not down:
        v |= LP_PREV | LP_TRANS
    return v


# 2026-10-28：原先这里还有 PEER_LABELS / SEARCH_BOX_DIP / SEARCH_FIRST_DIP /
# _label_for / _release_mouse —— 都是为「真实鼠标搜索切会话」准备的。那套方案
# 已经整段删除（见下面 say_pcm 的说明），这些定义一并清掉，不留空壳诱人用。

def _on_frida_message(msg: dict, data) -> None:
    """frida 脚本往 Python 抛的消息。

    ★ 2026-10-28：原来这一行是 `LOG.debug`，INFO 级别下全被吞掉 ——
      连"语音收件人已经被改写"这种关键动作都看不到一条日志，排查只能靠猜。
      现在 log 走 INFO、err 走 WARNING，其余仍留 DEBUG 免得刷屏。
    """
    payload = msg.get("payload")
    if isinstance(payload, dict):
        t = payload.get("t")
        if t == "log":
            LOG.info("frida: %s", payload.get("m"))
            return
        if t in ("err", "error"):
            LOG.warning("frida: %s", payload.get("msg"))
            return
        if t == "ok":
            LOG.info("frida: %s", payload.get("msg"))
            return
    if msg.get("type") == "error":
        LOG.warning("frida 脚本错误: %s", msg.get("description"))
    else:
        LOG.debug("frida: %s", payload if payload is not None else msg)


def find_wechat_window() -> int:
    return int(u32.FindWindowW(None, "微信") or 0)


def force_foreground(hwnd: int) -> bool:
    """把窗口强行切到前台（绕过 Windows 的前台锁）。

    ★ 2026-10-19 实测：「后台静默发语音」做不到 —— 语音靠 `PostMessage` 投递
      Alt 键给微信主窗口，而 Qt 只在窗口持有焦点时才把这个键盘消息路由给
      「按住说话」按钮。窗口没焦点时消息被静默丢弃，表现为 calls=0 / fed 0，
      微信那边看起来完全没反应。
      普通进程直接调 SetForegroundWindow 基本无效（返回 False 窗口不动），
      必须先把现任前台窗口的输入队列 attach 到自己线程，切完再 detach。
    """
    if not hwnd:
        return False
    fg = int(u32.GetForegroundWindow() or 0)
    if fg == hwnd:
        return True
    pid_fg = wintypes.DWORD()
    tid_fg = u32.GetWindowThreadProcessId(fg, ctypes.byref(pid_fg)) if fg else 0
    tid_me = int(k32.GetCurrentThreadId())
    ok = False
    try:
        if tid_fg and tid_fg != tid_me:
            u32.AttachThreadInput(tid_me, tid_fg, True)
        u32.BringWindowToTop(hwnd)
        ok = bool(u32.SetForegroundWindow(hwnd))
    except Exception:  # noqa: BLE001
        ok = False
    finally:
        if tid_fg and tid_fg != tid_me:
            try:
                u32.AttachThreadInput(tid_me, tid_fg, False)
            except Exception:  # noqa: BLE001
                pass
    return ok


def foreground_is_fullscreen() -> bool:
    """前台窗口是不是全屏（大概率是全屏游戏）。

    全屏的时候**不能**抢焦点 —— 会把游戏踢出全屏，比不发语音难受得多。
    """
    h = int(u32.GetForegroundWindow() or 0)
    if not h:
        return False
    r = wintypes.RECT()
    if not u32.GetWindowRect(h, ctypes.byref(r)):
        return False
    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    return r.left <= 0 and r.top <= 0 and r.right >= sw and r.bottom >= sh


def _pick_pid() -> int | None:
    try:
        procs = frida.get_local_device().enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    for p in procs:
        if "weixin" in (p.name or "").lower():
            return p.pid
    return None


class VoiceSender:
    """常驻的微信语音发送器。attach 一次，之后每次 say() 说一句。

    线程安全；微信重启或 hook 掉线时会自动重连一次。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
        self._script = None
        self._hwnd = 0

    # ---------- 连接管理 ----------
    def _connect(self) -> bool:
        pid = _pick_pid()
        if not pid:
            LOG.warning("找不到微信进程，语音不可用")
            return False
        try:
            session = frida.attach(pid)
            script = session.create_script(JS)
            script.on("message", _on_frida_message)
            script.load()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("frida attach 失败: %s", exc)
            return False
        self._session, self._script = session, script
        self._hwnd = find_wechat_window()
        LOG.info("语音通道就绪 pid=%d hwnd=%d", pid, self._hwnd)
        return True

    def _ensure(self) -> bool:
        if self._script is not None and self._hwnd and not self._hwnd_alive():
            LOG.warning("微信窗口失效，重连")
            self.close()
        if self._script is None:
            return self._connect()
        if not self._hwnd:
            self._hwnd = find_wechat_window()
        return bool(self._script and self._hwnd)

    def _hwnd_alive(self) -> bool:
        try:
            return u32.IsWindow(ctypes.c_void_p(self._hwnd)) != 0
        except Exception:  # noqa: BLE001
            return True

    def close(self) -> None:
        try:
            if self._session:
                self._session.detach()
        except Exception:  # noqa: BLE001
            pass
        self._session = self._script = None
        self._hwnd = 0

    # ---------- 发送 ----------
    @property
    def _ex(self):
        return getattr(self._script, "exports_sync", None) or self._script.exports

    def _ensure_visible(self) -> bool:
        """让微信窗口回到屏幕上（最小化或隐藏到托盘时）。

        ★ 2026-10-28 找到 calls=0 的一个真因就在这一条。点微信的关闭按钮或者按
          Win+D 之后，微信主窗口进的是 **SW_HIDE**（隐藏到托盘），而
          `IsIconic()` 这时返回 **False** —— 只判 IsIconic 的还原逻辑会完全跳过，
          窗口一句"没事"就过去了。可隐藏的窗口不渲染：输入框和「按住说话」
          按钮都不存在，Alt 投下去 Encode 一次都不会被调（calls=0 / fed 0）。

        ★ 用 **SW_SHOWNOACTIVATE**，不是 SW_SHOW：只让它出现在屏幕上，
          不抢前台、不夺焦点。语音靠 PostMessage 投递，本来就不需要前台，
          所以没必要把他的当前窗口顶掉。
        """
        hwnd = int(self._hwnd or 0)
        if not hwnd:
            return False
        if u32.IsWindowVisible(hwnd) and not u32.IsIconic(hwnd):
            return True
        LOG.info("微信窗口不可见（最小化或隐藏到托盘），无激活地放回屏幕")
        try:
            if u32.IsIconic(hwnd):
                u32.ShowWindow(hwnd, 4)     # SW_SHOWNOACTIVATE
            u32.ShowWindow(hwnd, 4)         # SW_SHOWNOACTIVATE
            time.sleep(0.6)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("还原微信窗口失败: %r", exc)
            return False
        ok = bool(u32.IsWindowVisible(hwnd))
        if not ok:
            LOG.warning("还原后微信窗口仍不可见")
        return ok

    # 2026-10-28：这里原本有 _dip / _click_dip / open_recent_chat 三个方法，
    # 干的是「用真实鼠标点搜索框、点联系人、点输入框，把会话切到目标再发语音」。
    # 已整段删除，理由写清楚免得以后又长回来：
    #   1. 语音功能的正身是「hook SILK 编码器 + 两条腿按键」，微信自己编码上传发送，
    #      全程不需要前台、不需要焦点、不需要动窗口（技术文档：不抢前台）。
    #   2. 真实鼠标会抢用户前台和输入法，文档 A3 记过事故 —— 他在输验证码时被打断。
    #   3. 实测这套点击还会把微信 Qt 整窗打成白屏（PrintWindow 白 98.7%，语音全挂）。
    #   4. 会话列表是 CEF 渲染的，PostMessage 鼠标消息被忽略，只能靠真实鼠标 ——
    #      也就是说这条路天生就得抢前台，和"不打扰他"根本对立。
    # 需要手动切会话时用 <PROJECT_ROOT>\sing\send_voice_robust.py（它的 open_chat 是
    # 显式可选的，SKIP_OPEN_CHAT=1 可跳过），不要在自动回复链路里做这件事。
    # 语音命中不了目标会话时，say_pcm 会在 2.5 秒内放弃，上层降级成文字。

    def say_pcm(self, pcm_path: Path, max_hold: float = 30.0, retries: int = 2,
                peer: str | None = None) -> bool:
        """把 16k 单声道 PCM 当语音发出去。失败自动重试。

        ★★ 2026-10-28 定案：**全程不碰 UI**。
          语音功能的正身是「hook SILK 编码器 + 两条腿按键」，靠微信自己
          编码/上传/发送；前台、焦点、窗口状态一概不需要动（技术文档原话：
          「hook SILK 编码器 + 真实按键，**不抢前台**」）。
          我之前为了"确保会话正确"加的抢前台、点搜索框、点联系人、点输入框，
          全都不在原设计里，而且有害：真实鼠标会抢用户前台和输入法
          （文档 A3 记过一次事故），一个 lParam 写错的合成按键还把微信
          整窗打成了白屏。
          现在的行为：直接发。微信停在别的会话就 calls=0，2.5 秒内放弃，
          上层降级成文字 —— 宁可不发，也不去动他的屏幕。

        ★ 语音只能发到「当前打开的会话」，这是微信的限制（文档 A8c）。
          想提高命中率就把微信停在<OWNER>那里，别指望程序替他切。

        ★ 重试 2 次：配合 probe_sec 快速失败，一次失手只花 2.5 秒，
          不再是过去那种干等 30 秒。

        ★★ 2026-10-28 多用户：给了 `peer` 就在 pack 提交点改写收件人，
          语音真正按 wxid 精确投递（原理见 JS 里 pack retarget 那段注释）。
          这意味着**不再要求"当前打开的会话就是收件人"**，只要微信开着一个
          正常的聊天窗口（有输入框）就能录，发给谁由我们决定。
        """
        pcm_path = Path(pcm_path)
        global _inflight
        with _inflight_lock:
            _inflight += 1
        try:
            return self._say_pcm_inner(pcm_path, max_hold, retries, peer)
        finally:
            with _inflight_lock:
                _inflight -= 1

    def _say_pcm_inner(self, pcm_path: Path, max_hold: float, retries: int,
                       peer: str | None) -> bool:
        if not self._ensure():
            return False
        # ★ 多人同时要语音时的排队顺序（2026-10-28 用户定的：随机）。
        #   录音通道全进程只有一条，_lock 保证串行，但谁先抢到锁取决于线程调度，
        #   实际上会偏向"先到先发"。这里在抢锁前随机让一让，让顺序真的随机。
        #   代价是单人也多等 0~2 秒 —— 语音本来就有拟人延迟，看不出来。
        if _voice_contention():
            time.sleep(random.uniform(0.0, 2.0))
        if peer:
            try:
                self._ex.setTarget(peer)
                LOG.info("语音目标 wxid = %s", peer)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("设置语音目标失败（退回按当前会话发）: %r", exc)
        try:
            for attempt in range(retries + 1):
                if self._say_once(pcm_path, max_hold):
                    return True
                if attempt < retries:
                    LOG.warning("语音发送失败（第 %d 次），%.1fs 后重试", attempt + 1, 1.2)
                    time.sleep(1.2)
            return False
        finally:
            # 必须清空：否则下一次没指定 peer 的发送会被上一次的目标污染
            try:
                self._ex.clearTarget()
            except Exception:  # noqa: BLE001
                pass

    def _say_once(self, pcm_path: Path, max_hold: float) -> bool:
        # ★ 必须转绝对路径：文件是**微信进程**去读的（frida 里的 File.readAllBytes），
        #   而那个进程的工作目录不是我们的项目目录。传相对路径会报
        #   "PCM 载入失败: No such file or directory"，看着像文件没生成，其实是找错地方了。
        pcm_path = Path(pcm_path).resolve()
        if not pcm_path.exists():
            LOG.warning("PCM 不存在: %s", pcm_path)
            return False
        expect = pcm_path.stat().st_size // 2
        if expect <= 0:
            LOG.warning("PCM 为空: %s", pcm_path)
            return False

        with self._lock:
            if not self._ensure():
                return False
            try:
                n = int(self._ex.loadfile(str(pcm_path)) or 0)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("PCM 载入失败: %s", exc)
                self.close()
                return False
            if n != expect:
                LOG.warning("PCM 载入样本数不符 %s != %s", n, expect)
                return False

            self._ex.arm()
            # 隐藏到托盘的窗口不渲染输入框，也就没有「按住说话」可触发。
            # 这只是把窗口放回屏幕，不是模拟点击，也不抢前台。
            self._ensure_visible()
            if foreground_is_fullscreen():
                LOG.warning("前台是全屏程序（多半在全屏游戏），这次不发语音")
                self._ex.disarm()
                return False

            # ★★ 按技术文档的实现：两条腿缺一不可（HANDOFF §语音消息 →「免前台」）
            #   ① keybd_event 让**系统键盘状态**里右 Alt 真的按下 —— 微信会校验这个
            #   ② PostMessage(WM_KEYDOWN) 把按键消息单独投递给微信窗口 —— 不需要它有焦点
            # 2026-10-28 三种按法实测，与文档数字完全吻合：
            #     纯 keybd_event        calls=51  16000/16000  成功
            #     纯 PostMessage        calls=12   3840/16000  失败 ← 文档说"只撑 12 帧"
            #     两条腿都上            calls=50  16000/16000  成功
            # 所以这里必须两条腿都上。**不抢前台、不点任何东西** —— 语音本来就不需要，
            # 前台从始至终可以停在浏览器上。
            u32.keybd_event(VK_RMENU, 0, EXT_KEY, None)
            u32.PostMessageW(self._hwnd, WM_KEYDOWN, ctypes.c_void_p(VK_RMENU),
                             ctypes.c_void_p(_ralt_lp(True)))

            done = False
            st: dict = {}
            # 微信没进录音态时，等满 max_hold 和等 2.5 秒的结论完全一样
            # （calls 始终 0）。2026-10-28 实测：切错会话后连等 30 秒 ×2 次
            # 纯属浪费他的时间，改成探测窗一过就放弃，把机会留给切会话重试。
            probe_sec = 2.5
            try:
                t0 = time.time()
                while time.time() - t0 < max_hold:
                    time.sleep(0.03)
                    pr = self._ex.progress()
                    if pr["cursor"] >= pr["total"] and pr["total"] > 0:
                        done = True
                        break
                    if pr["calls"] == 0 and time.time() - t0 >= probe_sec:
                        LOG.warning("按住说话没被触发（%.1fs 内 calls=0），提前放弃",
                                    probe_sec)
                        break
            except Exception as exc:  # noqa: BLE001
                LOG.warning("语音发送过程异常: %r", exc)
            finally:
                # ★ 清理必须无条件执行（审查 R05）：progress()/Frida RPC 一旦抛异常，
                #   旧代码会跳过松键和 disarm —— 系统里 Alt 一直按着、微信停在录音态，
                #   之后所有输入都不对。每步各自独立 try，一个失败不影响其余。
                # 松手也按文档来：投递 KEYUP + 真实抬起，同样两条腿。
                for name, fn in (
                    ("窗口 KEYUP", lambda: u32.PostMessageW(
                        self._hwnd, WM_KEYUP, ctypes.c_void_p(VK_RMENU),
                        ctypes.c_void_p(_ralt_lp(False)))),
                    ("系统 Alt 抬起", lambda: u32.keybd_event(
                        VK_RMENU, 0, EXT_KEY | KEYUP, None)),
                    ("hook disarm", lambda: st.update(self._ex.disarm() or {})),
                ):
                    try:
                        fn()
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("语音清理步骤「%s」失败（继续其余清理）: %r", name, exc)

            if done:
                LOG.info("语音已发出 %.2fs（%d 帧）", st.get("cursor", 0) / SR, st.get("calls", 0))
            else:
                LOG.warning("语音未发完: fed %s/%s calls=%s",
                            st.get("cursor"), st.get("total"), st.get("calls"))
            return done

    def say(self, text: str, mood: str | None = None, peer: str | None = None) -> bool:
        """合成并发送一句语音。mood 见 MOODS；未知档位回落到 FALLBACK_MOOD。

        ★ 未知档位必须**记日志**：之前是静默回退到「傲娇」，模型写了
          `[voice:害羞:...]` 也看不出来，结果情话配了冷语气（2026-10-27 实测）。

        ★ `peer` 只是签名占位：语音只能发给微信当前打开的会话，程序不能替它
          切（切会话必须真实鼠标，会抢前台、打断他 —— 见 say_pcm 的说明）。
          留着这个参数是为了调用方不必改，将来真做出精确投递再接。
        """
        mood = (mood or "").strip()
        if mood not in MOODS:
            if mood:
                LOG.warning("未知语音档位 %r，回退到「%s」（可选：%s）",
                            mood, FALLBACK_MOOD, "/".join(MOODS))
            mood = FALLBACK_MOOD
        try:
            pcm = synthesize_pcm(text, style=style_for(mood))
        except TTSError as exc:
            LOG.warning("语音合成失败: %s", exc)
            return False
        return self.say_pcm(pcm, peer=peer)


_sender: VoiceSender | None = None
_sender_lock = threading.Lock()


def get_sender() -> VoiceSender:
    """进程级单例。"""
    global _sender
    with _sender_lock:
        if _sender is None:
            _sender = VoiceSender()
        return _sender


def say(text: str, mood: str | None = None, peer: str | None = None) -> bool:
    return get_sender().say(text, mood, peer)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t = sys.argv[1] if len(sys.argv) > 1 else "喂，能听到吗？"
    m = sys.argv[2] if len(sys.argv) > 2 else None
    print("ok" if say(t, m) else "failed")
