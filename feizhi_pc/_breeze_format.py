"""确认 breeze 的输出格式选项，以及克隆音色合成时的真实表现。"""
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
VOICE = "voc_uj5qvdgfhuhz"      # 克隆得到的绯栀音色
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

TEXT = ("你今天到底几点睡的，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。"
        "[轻笑] 行行行，没困就没困。")
INSTR = ("用19岁女孩的口气，跟他撒娇又埋怨：前半句语速偏快、带点赌气，"
         "后半句软下来，尾音往下掉，藏一点心疼。不要念稿感。")

for fmt in ("wav", "mp3"):
    body = {"text": TEXT, "model_id": "breeze-tts-2", "language_code": "zh",
            "instructions": INSTR, "output_format": fmt}
    r = requests.post(BASE + "/v1/text-to-speech/" + VOICE, headers=H,
                      json=body, timeout=180)
    ctype = r.headers.get("Content-Type", "")
    head = r.content[:4] if r.status_code == 200 else b""
    print("output_format=%-4s HTTP %s  %-16s %7d 字节  头=%r"
          % (fmt, r.status_code, ctype, len(r.content), head))
    if r.status_code == 200 and ctype.startswith("audio"):
        p = OUT / ("I-克隆音色-带标签." + fmt)
        p.write_bytes(r.content)
        print("   已存:", p.name)
    elif r.status_code != 200:
        print("   ", (r.text or "")[:200])
