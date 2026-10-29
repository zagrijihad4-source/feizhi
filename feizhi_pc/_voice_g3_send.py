# -*- coding: utf-8 -*-
"""把 J1 批次里最值得听的 4 条发给<OWNER>，供人耳判定。

挑法：
  BASE  参照（无 instructions），一切的基准
  开心   F0 +29.3%，超出噪声两倍，音高确实被抬走了
  害羞   sd 102.2 / 帧间跳 11.6，抖动最厉害
  娇嗔   帧间跳 12.0，也是抖 + 静音 19.9%
"""
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts      # noqa: E402
import voice    # noqa: E402
from bridge import HookBridge   # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
PEER = "<WXID_FRIEND_A>"
PICKS = ["BASE-1", "开心-1", "害羞-1", "娇嗔-1"]

# 语音条没有文字，先打一句说明顺序，不然听完对不上
HookBridge().send_text(
    PEER, "接着 4 条语音，顺序是：基准（无指令）/ 开心 / 害羞 / 娇嗔。同一句话，只换语气指令。")

sender = voice.VoiceSender()
if not sender._ensure():
    print("hook 不可用")
    raise SystemExit(2)

for name in PICKS:
    wav_path = OUT / ("J1-%s.wav" % name)
    if not wav_path.exists():
        print("缺文件:", wav_path)
        continue
    pcm = ROOT / "tmp" / ("_j1_%s.pcm" % name)
    tts.to_wechat_pcm(wav_path.read_bytes(), pcm)
    ok = sender.say_pcm(pcm, max_hold=40.0, peer=PEER)
    print("%-8s %s" % (name, "已发" if ok else "失败"), flush=True)
sender.close()
