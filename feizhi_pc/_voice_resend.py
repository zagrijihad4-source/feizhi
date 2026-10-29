"""重发失败那条：先主动点会话 + 点输入框，把焦点拿回来。

连续发送时第二条常报 calls=0 —— 上一条发完后焦点被带走，
而 say_pcm 只在重试时才补救，第一次仍会白跑 30 秒。
"""
import sys
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
wav = OUT / "I3-无指令g2.wav"
pcm = ROOT / "tmp" / "_i_I3.pcm"
tts.to_wechat_pcm(wav.read_bytes(), pcm)
print("pcm %.1f 秒" % (pcm.stat().st_size / 32000.0))

sender = voice.VoiceSender()
sender._ensure()
print("先点会话与输入框，拿回焦点…")
sender.open_recent_chat()
time.sleep(1.0)
sent = sender.say_pcm(pcm, max_hold=45.0, retries=1)
print("sent =", sent)
