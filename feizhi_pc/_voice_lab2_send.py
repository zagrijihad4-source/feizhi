"""发第二版对照（E / F）到微信。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_FRIEND_A>"
SEQ = [
    ("E", ROOT / "tmp" / "_vt2_E.pcm", "第一条：指令写到具体声音动作，guidance 2"),
    ("F", ROOT / "tmp" / "_vt2_F.pcm", "第二条：加了身体状态和情境，guidance 3"),
]

b = bridge.HookBridge()
ok = b.send_text(PEER, "第二版对照，两条。第一条偏「动作」（往上挑、笑到一半收住），第二条偏「状态」（刚被吵醒、气息比声音多）。")
print("标注:", ok)
time.sleep(2.5)

sender = voice.VoiceSender()
for tag, pcm, label in SEQ:
    if not pcm.exists():
        print("缺:", pcm)
        continue
    t0 = time.time()
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%s %.1fs sent=%s (%.1fs)  %s"
          % (tag, pcm.stat().st_size / 32000.0, sent, time.time() - t0, label))
    time.sleep(1.6)
