"""Send the RVC cover to WeChat as a voice message.

Steps: open (and confirm) the chat with YG via one text line, then feed the
16k mono PCM through the existing voice hook.

usage: python sing_to_wx.py <pcm> [intro text] [max_hold]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

PEER = "<WXID_FRIEND_A>"  # YG

pcm = Path(sys.argv[1])
intro = sys.argv[2] if len(sys.argv) > 2 else "给你唱一段潮汐"
hold = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0

import bridge
import voice

print("pcm      :", pcm, pcm.stat().st_size // 2 / 16000.0, "s")
b = bridge.HookBridge()
print("worker   :", b.worker_healthy())
age = b.ctx_age_sec()
print("ctx_age  :", None if age is None else round(age, 1), "s")

if intro:
    ok = b.send_text(PEER, intro)
    print("intro    :", ok)
    time.sleep(2.5)

hwnd = voice.find_wechat_window()
print("wechat   :", hwnd)
t0 = time.time()
sent = voice.VoiceSender().say_pcm(pcm, max_hold=hold, retries=1)
print("voice    :", sent, "in %.1fs" % (time.time() - t0))
