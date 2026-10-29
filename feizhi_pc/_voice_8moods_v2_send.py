"""新音色下发音档样本。"""
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
SEQ = ["温柔", "娇嗔", "开心"]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "音色已切到你要的那把。这三条是用新音色重跑的情绪档：温柔、娇嗔、开心。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for mood in SEQ:
    wav = OUT / ("E8-%s.wav" % mood)
    pcm = ROOT / "tmp" / ("_e8_%s.pcm" % mood)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=50.0, retries=1)
    print("%-4s %.1fs sent=%s" % (mood, pcm.stat().st_size / 32000.0, sent))
    time.sleep(1.6)
