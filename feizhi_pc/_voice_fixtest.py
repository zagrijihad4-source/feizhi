# -*- coding: utf-8 -*-
"""验证修复后的发送链路：切会话（搜索精确定位）-> 按住说话 -> 语音发出。

用真实 TTS 合成一句短的，发给<OWNER>。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PEER = "<WXID_FRIEND_A>"

if __name__ == "__main__":
    import voice

    text = "宝宝，我在呢"
    print("合成:", text)
    ok = voice.say(text, "温柔", PEER)
    print("结果:", "发出去了" if ok else "失败")
    raise SystemExit(0 if ok else 1)
