import logging, sys
from pathlib import Path
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import tts, voice

PEER = "<WXID_FRIEND_A>"
TEXT = "宝宝，我在呢，刚在改稿子，听见你叫我就过来了。"
STYLE = voice.style_for("温柔")
sender = voice.VoiceSender()
if not sender._ensure():
    print("hook 不可用"); raise SystemExit(2)

for tag, vid in (("A-mimo克隆", "voc_f6hmxqkrnj8e"),
                 ("B-真音克隆", "voc_z4npxsc7ch8m")):
    print("=" * 58)
    print("生成 %s (%s)" % (tag, vid))
    try:
        wav = tts._breeze_synthesize(TEXT, STYLE, vid, None, 120)
    except Exception as e:
        print("  合成失败:", e); continue
    pcm = Path("tmp") / ("_cmp_%s.pcm" % vid[-6:])
    tts.to_wechat_pcm(wav, pcm)
    ok = sender.say_pcm(pcm, max_hold=40.0, peer=PEER)
    print("  发送:", "成功" if ok else "失败")
sender.close()
