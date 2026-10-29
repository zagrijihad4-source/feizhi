"""发 mimo 版给用户对比（同文本同 style）。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_FRIEND_A>"
b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER, "这条是 MiMo 出的，同一句话、同一个克隆音色、同一套指令。跟上面那条 breeze 的对比着听。"))
time.sleep(2.5)

pcm = ROOT / "tmp" / "_cmp_mimo.pcm"
sender = voice.VoiceSender()
sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
print("mimo %.1fs sent=%s" % (pcm.stat().st_size / 32000.0, sent))
