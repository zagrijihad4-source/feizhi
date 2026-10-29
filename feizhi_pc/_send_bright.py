import logging, sys
from pathlib import Path
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import tts, voice

PEER = "<WXID_FRIEND_A>"
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
sender = voice.VoiceSender()
if not sender._ensure():
    print("hook 不可用"); raise SystemExit(2)
for tag in ("AAA-明快", "BBB-带笑"):
    wav = OUT / ("%s.wav" % tag)
    if not wav.exists():
        print(tag, "缺文件"); continue
    pcm = Path("tmp") / ("_%s.pcm" % tag)
    tts.to_wechat_pcm(wav.read_bytes(), pcm)
    ok = sender.say_pcm(pcm, max_hold=60.0, peer=PEER)
    print("%-10s -> %s" % (tag, "已发" if ok else "失败"), flush=True)
sender.close()
