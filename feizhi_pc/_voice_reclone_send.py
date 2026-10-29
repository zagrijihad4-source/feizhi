"""发新旧音色对比。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import tts  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_TYPO_A>"
PEER = "<WXID_FRIEND_A>"
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
SEQ = [("旧-合成样本", "第一条：旧音色（voicedesign 合成的「冷清慵懒」样本克隆）"),
       ("新-真实样本", "第二条：新音色（用音音子真实分离人声 yy_12 克隆）")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER, "换了克隆样本。第一条是之前那个合成样本，第二条换成音音子本人的真实录音。同一句台词、同一段指令。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ("BB-%s.wav" % tag)
    pcm = ROOT / "tmp" / ("_bb_%s.pcm" % tag.split("-")[1])
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=50.0, retries=1)
    print("%-10s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
