"""发 Z1（旧指令带身份）vs Z3（教程轻巧撒娇）。"""
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
SEQ = [("Z1", "第一条：旧指令（里面写了「19岁杭州女孩、音色中低偏清冷」）"),
       ("Z3", "第二条：教程配方「轻巧撒娇」，指令里没有一句提到声音身份")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER,
    "同一句台词「你回来啦，我等你好久了。」。第一条是我之前的指令（带声音身份描述），"
    "第二条按教程配方写，只描述表演。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, label in SEQ:
    wav = OUT / ({"Z1": "Z1-旧指令-带身份", "Z3": "Z3-教程轻巧撒娇"}[tag] + ".wav")
    pcm = ROOT / "tmp" / ("_z_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%s %.1fs sent=%s  %s" % (tag, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
