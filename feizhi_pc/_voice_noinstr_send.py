"""发无指令对照（guidance 1 vs 5）。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import tts  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_FRIEND_A>"
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
SEQ = [("X1", "不带指令，guidance 1（默认）"),
       ("X2", "不带指令，guidance 5")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "用你给的那句原文试了两条，这次**完全不传指令**，让模型自己看着文本演。"
    "第一条 guidance 默认，第二条 guidance 5。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ({"X1": "X1-无指令-g1", "X2": "X2-无指令-g5"}[tag] + ".wav")
    pcm = ROOT / "tmp" / ("_x_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
