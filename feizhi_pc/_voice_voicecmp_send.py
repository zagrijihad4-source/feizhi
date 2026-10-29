"""发音色对照：克隆 vs Deema vs Raina。"""
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
SEQ = [
    ("克隆-绯栀", "第一条：现在用的克隆音色（绯栀）"),
    ("Deema", "第二条：预设音色 Deema"),
    ("Raina", "第三条：预设音色 Raina"),
]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "同一句话、都不传指令，只换音色。第一条是克隆的绯栀，后两条是 breeze 自带音色。"
    "重点听语气活不活，不看音色像不像。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ("Y-%s.wav" % tag)
    if not wav.exists():
        print("缺:", wav)
        continue
    pcm = ROOT / "tmp" / ("_y2_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%-10s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
