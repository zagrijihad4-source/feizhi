# -*- coding: utf-8 -*-
"""实验：Breeze 能不能在**句内**变速。

用户的原话是「ai说话不会变速」。`voice_settings.speed` 只能整体变速，
所以要验证的是：**instructions 里的快慢描述，能不能让一句话内部产生快慢差异**。

做法：同一段文本分三个短句，给三种不同的快慢指令，生成后量每一句的实际时长。
同样的字数，时长不同 = 语速不同。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts   # noqa: E402

VID = "voc_f6hmxqkrnj8e"
TEXT = "宝宝，我在呢。刚在改稿子。听见你叫我就过来了。"
# 三句字数：6 / 6 / 10
SENT_CHARS = [6, 6, 10]

CASES = [
    ("plain", None),
    ("faster-then-slow",
     "整段话要有明显的快慢变化：第一句说得又快又急，像抢着开口；"
     "第二句明显放慢，一个字一个字地说；第三句回到平常语速。"),
    ("slow-then-faster",
     "整段话要有明显的快慢变化：第一句很慢，像还没想好；"
     "第二句开始加快；第三句又快又连。"),
]


def measure(wav_bytes: bytes, tag: str) -> dict:
    """用 silencedetect 找停顿，把语音切成段，返回每段时间与估算字速。"""
    tmp = Path(tempfile.mkdtemp())
    wav = tmp / ("%s.wav" % tag)
    wav.write_bytes(wav_bytes)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(wav), "-af",
         "silencedetect=noise=-40dB:d=0.12", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = r.stderr or ""
    sil = [(float(m.group(1)), float(m.group(2)))
           for m in re.finditer(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", log, re.S)]
    dur = None
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", log)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    # 语音段 = 去掉静音后的区间
    segs = []
    cur = 0.0
    for s, e in sil:
        if s > cur + 0.02:
            segs.append((cur, s))
        cur = max(cur, e)
    if dur and dur > cur + 0.02:
        segs.append((cur, dur))
    out = []
    for i, (s, e) in enumerate(segs):
        out.append({"start": round(s, 2), "len": round(e - s, 2)})
    return {"dur": dur, "silence": len(sil), "segs": out}


def main() -> int:
    print("文本：%s（三句 %s 字）" % (TEXT, SENT_CHARS))
    print("voice_id:", VID)
    for tag, instr in CASES:
        try:
            wav = tts._breeze_synthesize(TEXT, instr, VID, None, 120)
        except Exception as exc:  # noqa: BLE001
            print("%-18s 合成失败 %r" % (tag, exc))
            continue
        info = measure(wav, tag)
        print("=" * 66)
        print("%-18s 总长 %.2fs  停顿 %d 处" % (tag, info["dur"] or 0, info["silence"]))
        segs = info["segs"]
        if len(segs) >= 2:
            # 把语音段按字数分配到三句（近似）
            total_speech = sum(x["len"] for x in segs)
            print("  语音段（共 %d 段，语音总长 %.2fs）：" % (len(segs), total_speech))
            for x in segs[:6]:
                print("    起点 %5.2fs  时长 %5.2fs" % (x["start"], x["len"]))
            # 粗估：按语音段数量判断快慢分布
            if len(segs) >= 3:
                a, b, c = segs[0]["len"], segs[1]["len"], segs[2]["len"]
                print("  前/中/后 段时长比：%.2f : %.2f : %.2f" % (a, b, c))
                print("  → %s" % ("存在明显快慢差" if max(a, b, c) / max(0.01, min(a, b, c)) > 1.5
                                  else "三段时长接近，未见句内变速"))
        else:
            print("  只检测到 %d 段语音，句子之间没有停顿" % len(segs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
