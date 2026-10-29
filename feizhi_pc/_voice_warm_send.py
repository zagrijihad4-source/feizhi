"""发克制版 vs 外放版对照。"""
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
SEQ = [("Q", "第一条：现在生产用的温柔档（音量轻、尾音下压、不要煽情）"),
       ("R", "第二条：把抑制词全换掉（音量正常、尾音上扬、笑出来不收）")]

b = bridge.HookBridge()
print("标注:", b.send_text(PEER, "情绪对照两条，同一句话。第一条是现在生产在用的版本，第二条是去掉所有「克制」措辞后的版本。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ({"Q": "Q-现用温柔档", "R": "R-外放热情"}[tag] + ".wav")
    if not wav.exists():
        print("缺:", wav)
        continue
    pcm = ROOT / "tmp" / ("_warm_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
