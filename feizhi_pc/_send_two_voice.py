# -*- coding: utf-8 -*-
"""发两条语音给<OWNER>听音色。

温柔（刚去掉情境绑定）和娇嗔各一条，内容都取轻松日常，
不碰"安慰人"那种场景 —— 用来判断语气是否回到她平时的样子。
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import voice  # noqa: E402

PEER = "<WXID_FRIEND_A>"
CASES = [
    ("温柔", "宝宝，我在呢，刚在改稿子，听见你叫我就过来了。"),
    ("娇嗔", "你就顾着打游戏，也不问问我在干嘛。"),
]

ok_n = 0
for mood, text in CASES:
    print("=" * 60)
    print("发 %s：%s" % (mood, text))
    if voice.say(text, mood, PEER):
        ok_n += 1
        print("  -> 成功")
    else:
        print("  -> 失败")
print("=" * 60)
print("成功 %d / %d" % (ok_n, len(CASES)))
