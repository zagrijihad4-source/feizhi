"""把指定 PCM 当微信语音发出去。用法: python send_pcm.py <pcm路径> [最长按秒]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

pcm = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"<PROJECT_ROOT>\sing\outputs\taoxi\cover16k.pcm")
hold = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

if not pcm.exists():
    raise SystemExit("没有这个 PCM: %s" % pcm)
n = pcm.stat().st_size // 2
print("PCM %s  %.2fs" % (pcm.name, n / 16000.0))

import voice

print("微信窗口 =", voice.find_wechat_window())
t0 = time.time()
ok = voice.VoiceSender().say_pcm(pcm, max_hold=hold, retries=1)
print("发送 =", ok, " 耗时 %.1fs" % (time.time() - t0))
