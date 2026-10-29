# -*- coding: utf-8 -*-
"""诊断：为什么她会唱歌，却对 <PEER_TEST> 的「唱个歌我听听」不唱。

对照两档关系（stranger / intimate），同一个请求，看模型是否输出 [sing:]。
不发送任何消息，只生成。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import sing                       # noqa: E402
from llm import LLMClient          # noqa: E402
from persona import style_block    # noqa: E402

SONGS = sing.catalog_text()
SONG_BLOCK = (
    "\n\n【你唱过的歌】\n"
    "你自己录过这几首：" + SONGS + "，都存在手机里。\n"
    "★ 他说「唱首歌」「给我唱一个」「唱来听听」的时候，"
    "整条回复只写 `[sing:曲名]`。微信会把它当成一条语音条发出去，"
    "那才是你真正在唱。\n"
    "★ **不要用 `[voice:]` 把歌词念出来** —— 念词不是唱歌，他听得出来。\n"
)

CASES = [
    ("stranger", "<PEER_TEST>", "唱个歌我听听"),
    ("intimate", "<OWNER>", "唱个歌我听听"),
    ("stranger", "<PEER_TEST>", "给我唱首歌行不行"),
]

llm = LLMClient()
print("曲库：%r" % SONGS)
for relation, name, ask in CASES:
    system = style_block(include_emoji=True, relation=relation, peer_name=name) + SONG_BLOCK
    try:
        out = llm.chat(system, "%s：%s" % (name, ask), max_tokens=400)
    except Exception as exc:  # noqa: BLE001
        print("[%s/%s] %r -> 调用失败 %r" % (relation, name, ask, exc))
        continue
    hit = "[sing:" in (out or "")
    print("=" * 66)
    print("[%s] %r   -> %s" % (relation, ask, "★ 唱了" if hit else "没唱"))
    print((out or "").strip()[:300])
