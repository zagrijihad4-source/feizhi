"""发语速校准的两条对照（speed 1.0 / 1.3）。"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import bridge  # noqa: E402
import tts  # noqa: E402
import voice  # noqa: E402

PEER = "<WXID_TYPO_B>"   # 占位，下面从 store 取真实 peer
PEER = "<WXID_FRIEND_A>"

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
SEQ = [("P-s10", "speed 1.0，语速 4.1 字/秒（正常口语）"),
       ("P-s13", "speed 1.3，语速 6.0 字/秒（偏快）")]

b = bridge.HookBridge()
print("标注:", b.send_text(
    PEER, "语速对照两条：第一条 speed 1.0（正常语速），第二条 speed 1.3（偏快）。这次去掉了叹气标签。"))
time.sleep(2.5)

sender = voice.VoiceSender()
for stem, label in SEQ:
    wav = OUT / (stem + ".wav")
    if not wav.exists():
        print("缺:", wav)
        continue
    pcm = ROOT / "tmp" / ("_%s.pcm" % stem)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
    print("%-6s %.1fs sent=%s  %s"
          % (stem, pcm.stat().st_size / 32000.0, sent, label))
    time.sleep(1.6)
