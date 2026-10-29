"""发收敛测试的两条。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
b = bridge.HookBridge()
print("标注:", b.send_text(
    "<WXID_FRIEND_A>",
    "往「自然」那个方向收的两条：第一条 guidance 2，第二条完全不传指令。"
    "另外发现一件事：同样的参数，两次生成的起伏能差一倍。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for name in ("I1-温柔g2", "I3-无指令g2"):
    wav = OUT / (name + ".wav")
    pcm = ROOT / "tmp" / ("_i_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%-12s %.1fs sent=%s" % (name, pcm.stat().st_size / 32000.0, sent))
    time.sleep(1.6)
