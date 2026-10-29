"""发 guidance 4 / 6 对照。"""
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
SEQ = [("U2", "guidance 4.0"), ("U3", "guidance 6.0")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "这轮修了引导强度（官方示例用 4.0，我之前一直用的默认 1.0）。"
    "两句都是「前亮后软」的起伏设计，第一条 guidance 4，第二条 guidance 6。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ({"U2": "U2-起伏设计-g4", "U3": "U3-起伏设计-g6"}[tag] + ".wav")
    pcm = ROOT / "tmp" / ("_u_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=50.0, retries=1)
    print("%s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
