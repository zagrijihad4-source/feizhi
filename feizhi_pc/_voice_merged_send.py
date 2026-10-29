"""发 M1 / M3。"""
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
SEQ = [("M1", "合并配方 guidance 4（静音最少那版）"),
       ("M3", "合并配方 guidance 8（起伏最大那版）")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "把教程的结构和之前那两版的「段内起伏」合起来了，都没写声音身份。"
    "第一条 guidance 4，第二条 guidance 8。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ({"M1": "M1-合并-g4", "M3": "M3-合并-g8"}[tag] + ".wav")
    pcm = ROOT / "tmp" / ("_m_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=50.0, retries=1)
    print("%s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
