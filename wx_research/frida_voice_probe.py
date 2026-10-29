# -*- coding: utf-8 -*-
"""SILK 编码器参数探测 —— 确定微信语音消息的采样率与帧长。

已确认：微信 4.1.9.23 语音消息走 SILK v3，编码器是 VoipEngine.dll 导出的
SKP_Silk_SDK_Encode，且 Weixin.dll 通过 GetProcAddress 动态获取它。

SKP_Silk_SDK_Encode 签名（SILK SDK 1.0.9）：
    SKP_int SKP_Silk_SDK_Encode(
        void *psEnc,                                     // arg0 编码器状态
        const SKP_SILK_SDK_EncControlStruct *encControl,  // arg1 控制结构
        const SKP_int16 *samplesIn,                       // arg2 PCM 输入 ← 我们的替换点
        SKP_int32 nSamplesIn,                             // arg3 本帧样本数
        SKP_uint8 *outData,                               // arg4 输出缓冲
        SKP_int16 *nBytesOut);                            // arg5 输出字节数

EncControlStruct 布局：API_sampleRate(+0) maxInternalSampleRate(+4)
                       packetLossPercentage(+8) complexity(+12)
                       useInBandFEC(+16) useDTX(+20) useCBR(+24)

用法：python frida_voice_probe.py --seconds 120
然后在微信里按住右 Alt 录一条语音并发送。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import frida

OUT = Path(r"<PROJECT_ROOT>\tmp\voice_params.txt")

JS = r"""
'use strict';

function exp(name) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(name); } catch (e) {}
    try { return Module.findExportByName(null, name); } catch (e) {}
    return null;
}

var mods = [];
function where(addr) {
    try {
        var m = Process.findModuleByAddress(addr);
        if (!m) return addr.toString();
        return m.name + '+0x' + addr.sub(m.base).toString(16);
    } catch (e) { return '?'; }
}

var stats = { calls: 0, frames: 0, sampleCounts: {}, rates: {}, firstDetail: null };
var DETAIL_LIMIT = 6;
var detailSent = 0;

var voip = Process.findModuleByName('VoipEngine.dll');
if (!voip) { send({ t: 'err', msg: 'VoipEngine.dll not loaded' }); }
else {
    var pInit = voip.findExportByName('SKP_Silk_SDK_InitEncoder');
    var pEnc  = voip.findExportByName('SKP_Silk_SDK_Encode');

    send({ t: 'info', msg: 'VoipEngine base=' + voip.base + ' InitEncoder=' + pInit + ' Encode=' + pEnc });

    if (pInit) {
        Interceptor.attach(pInit, {
            onEnter: function (a) {
                try {
                    var rate = a[1].readS32();
                    send({ t: 'init', msg: 'InitEncoder API_sampleRate=' + rate });
                } catch (e) { send({ t: 'init', msg: 'InitEncoder (arg read failed: ' + e + ')' }); }
            }
        });
    }

    Interceptor.attach(pEnc, {
        onEnter: function (a) {
            this.psEnc = a[0];
            this.ctl = a[1];
            this.pcm = a[2];
            this.n = a[3].toInt32();
            this.out = a[4];
            this.nOut = a[5];
            stats.calls++;
            stats.frames += this.n;

            var rate = -1;
            try { rate = this.ctl.readS32(); } catch (e) {}
            var key = 'n=' + this.n + ' rate=' + rate;
            stats.sampleCounts[key] = (stats.sampleCounts[key] || 0) + 1;
            stats.rates[rate] = (stats.rates[rate] || 0) + 1;

            if (detailSent < DETAIL_LIMIT) {
                detailSent++;
                var samples = [];
                try {
                    for (var i = 0; i < Math.min(24, this.n); i++) {
                        samples.push(this.pcm.add(i * 2).readS16());
                    }
                } catch (e) { samples.push('err:' + e); }
                var ctl = [];
                try {
                    for (var k = 0; k < 7; k++) ctl.push(this.ctl.add(k * 4).readS32());
                } catch (e) { ctl.push('err'); }
                send({
                    t: 'detail', idx: detailSent,
                    pcm: this.pcm.toString(),
                    n: this.n, rate: rate,
                    ctl: ctl.join(','),
                    samples: samples.join(','),
                    out: this.out.toString(),
                    bt: Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 7).map(where).join(' <- ')
                });
            }
        },
        onLeave: function (retval) {
            try {
                if (detailSent <= DETAIL_LIMIT && this.nOut) {
                    send({ t: 'outBytes', idx: detailSent, bytes: this.nOut.readS16() });
                }
            } catch (e) {}
        }
    });
    send({ t: 'hooked', msg: 'SKP_Silk_SDK_Encode hooked' });
}

// 超时后由 Python 侧打印统计；这里响应查询
recv('stats', function () {
    send({ t: 'stats', calls: stats.calls, frames: stats.frames,
           sampleCounts: stats.sampleCounts, rates: stats.rates });
});
"""


def pick_pids() -> list[int]:
    try:
        procs = frida.get_local_device().enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    return [p.pid for p in procs if "weixin" in (p.name or "").lower()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    args = ap.parse_args()

    lines: list[str] = []

    def emit(s: str) -> None:
        lines.append(s)
        print(s, flush=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")

    pids = pick_pids()
    if not pids:
        print("没有 Weixin 进程")
        return 1
    emit("=== SILK 参数探测 @ %s ===" % time.strftime("%H:%M:%S"))
    emit("目标: %s" % pids)

    sessions = []
    for pid in pids:
        try:
            sess = frida.attach(pid)
            sc = sess.create_script(JS)

            def on_msg(m, _d, _pid=pid):
                if m.get("type") != "send":
                    return
                p = m["payload"]
                t = p.get("t")
                if t == "detail":
                    emit("[%d] FRAME#%d n=%d rate=%d ctl=[%s]" % (_pid, p["idx"], p["n"], p["rate"], p["ctl"]))
                    emit("      pcm@%s out@%s" % (p["pcm"], p["out"]))
                    emit("      first samples: %s" % p["samples"])
                    emit("      bt: %s" % p["bt"])
                elif t == "outBytes":
                    emit("[%d]      -> encoded %d bytes" % (_pid, p["bytes"]))
                elif t == "stats":
                    emit("[%d] total Encode calls=%d  total samples=%d" % (_pid, p["calls"], p["frames"]))
                    emit("      n/rate 分布: %s" % p["sampleCounts"])
                elif t == "err":
                    emit("[%d] ERR %s" % (_pid, p["msg"]))
                else:
                    emit("[%d] %s %s" % (_pid, t.upper(), p.get("msg", "")))

            sc.on("message", on_msg)
            sc.load()
            sessions.append((pid, sess, sc))
        except Exception as exc:  # noqa: BLE001
            emit("[%d] attach 失败: %s" % (pid, exc))

    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        emit("(中断)")
    for pid, sess, sc in sessions:
        try:
            sc.post({"type": "stats"})
        except Exception:
            pass
    time.sleep(1.5)
    for _pid, sess, _sc in sessions:
        try:
            sess.detach()
        except Exception:
            pass
    emit("=== 结束 ===")
    print("-> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
