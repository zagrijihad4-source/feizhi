# -*- coding: utf-8 -*-
"""诊断 AI 感：用真实 generator 跑一遍 <PEER_TEST> 那类对话，看她还会不会像客服。

只生成，不发送。重点看三件事：
  1. 有没有客服腔（帮不上 / 这边 / 功能 / 我是普通人）
  2. 会不会每轮重复反问「你是谁」
  3. 一句话被拆成几条发
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from autoreply import FeizhiReplyGenerator     # noqa: E402
from llm import LLMClient                      # noqa: E402

BANNED = ("帮不上", "这边", "功能", "普通人", "机器人", "客服", "不方便说")

HISTORY = [
    ("user", "hi"),
    ("assistant", "晚上好呀，不过……你好像认错人了？我这边没存到你。请问你是哪位呀，找我有什么事吗？"),
    ("user", "帮我上班"),
    ("assistant", "诶，这个我帮不了呀，我连自己作业都拖到现在。"),
]

CASES = [
    "你是谁",
    "烦死了",
    "你他妈是自动回复不",
    "你头像很丑",
    "唱个歌我听听",
]

gen = FeizhiReplyGenerator(llm=LLMClient(), timeout=60, attempts=2)
gen.relation = "stranger"
gen.peer_name = "<PEER_TEST>"

for ask in CASES:
    try:
        plan = gen.generate_plan(ask, list(HISTORY))
    except Exception as exc:  # noqa: BLE001
        print("=" * 70)
        print("<PEER_TEST>：%s\n  -> 生成失败 %r" % (ask, exc))
        continue
    msgs = [getattr(m, "text", "") or "" for m in (plan.messages or [])]
    joined = " / ".join(msgs)
    bad = [w for w in BANNED if any(w in t for t in msgs)]
    print("=" * 70)
    print("<PEER_TEST>：%s" % ask)
    print("  条数=%d%s" % (len(msgs), "   ★ 拆太多" if len(msgs) > 3 else ""))
    for t in msgs:
        print("    · %s" % t)
    if bad:
        print("  ⚠ 客服腔：%s" % "、".join(bad))
    if "唱" in ask:
        print("  %s" % ("★ 输出 [sing:]" if "[sing:" in joined else "✗ 没唱"))
