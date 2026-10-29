# -*- coding: utf-8 -*-
"""验证两处修复：不替他升级行为、语气跟随真实对话。

用<OWNER>的真实历史（intimate 档），只生成不发送。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from autoreply import FeizhiReplyGenerator     # noqa: E402
from llm import LLMClient                      # noqa: E402
from store import ContextStore                 # noqa: E402

PEER = "<WXID_FRIEND_A>"
st = ContextStore()
hist = st.history(PEER, limit=14)

gen = FeizhiReplyGenerator(llm=LLMClient(), timeout=60, attempts=2)
gen.relation = "intimate"
gen.peer_name = "<OWNER>"
gen.context_text = ""
gen.memory_ctx = ""
gen.search_ctx = ""
try:
    from peer_state import get_registry
    life = get_registry().get(PEER).life
    life.reload_shared()
    gen.life_ctx = life.render(include_loops=False)
except Exception as e:  # noqa: BLE001
    gen.life_ctx = ""
    print("life 渲染失败:", e)

CASES = [
    "在打游戏呢",
    "你用语音回我两句好不好，想听你说话了",
]
BAD = ("又开一局", "瘾", "第几把", "打到几")

for ask in CASES:
    plan = gen.generate_plan(ask, list(hist))
    msgs = [str(getattr(m, "text", "") or "") for m in (plan.messages or [])]
    joined = " / ".join(msgs)
    print("=" * 68)
    print("<OWNER>：%s   （她 %d 条）" % (ask, len(msgs)))
    for m in msgs:
        print("    · %s" % m)
    hits = [w for w in BAD if w in joined]
    if hits:
        print("  ⚠ 仍在替他升级：%s" % "、".join(hits))
    if "[voice:" in joined:
        import re
        m = re.search(r"\[voice:([^:\]]+):", joined)
        print("  ★ 语音档位：%s" % (m.group(1) if m else "（无档位）"))
