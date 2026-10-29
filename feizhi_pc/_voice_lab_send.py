"""把对照语音发到微信，并先发一句文字标注顺序。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_FRIEND_A>"
SEQUENCE = [
    ("A 长三段式（现在生产用的）", ROOT / "tmp" / "_vt_A.pcm"),
    ("B 短一句（官方文档推荐的写法）", ROOT / "tmp" / "_vt_B.pcm"),
]

b = bridge.HookBridge()
print("worker_healthy:", b.worker_healthy())
ok = b.send_text(PEER, "语音对照，一共两条：第一条是现在生产在用的长指令，第二条是官方文档推荐的短指令。")
print("标注文字:", ok)
time.sleep(2.5)

sender = voice.VoiceSender()
for label, pcm in SEQUENCE:
    if not pcm.exists():
        print("缺文件:", pcm)
        continue
    dur = pcm.stat().st_size / 32000.0
    t0 = time.time()
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%-34s %.1fs -> sent=%s  (%.1fs)" % (label, dur, sent, time.time() - t0))
    time.sleep(1.6)
