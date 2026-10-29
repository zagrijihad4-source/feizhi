"""breeze 最终实测：中文音频标签 + instructions + guidance_scale。

对比三组，看标签和 guidance_scale 各自贡献多少：
  E 无标签、无 guidance
  F 带 [叹气] 标签
  G 带标签 + guidance_scale=3
"""
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
VOICE = "voc_9k38qhkc6qrm"   # Deema

INSTR = ("用19岁女孩的口气，跟他撒娇又埋怨：前半句语速偏快、带点赌气，"
         "后半句软下来，尾音往下掉，藏一点心疼。不要念稿感。")

CASES = [
    ("E-breeze-无标签", "你今天到底几点睡的，眼睛都睁不开了吧，还嘴硬说没困。", None),
    ("F-breeze-带叹气标签", "你今天到底几点睡的，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。", None),
    ("G-breeze-标签+guidance3", "你今天到底几点睡的，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。", 3.0),
]

for name, text, gs in CASES:
    body = {"text": text, "model_id": "breeze-tts-2", "language_code": "zh",
            "instructions": INSTR}
    if gs is not None:
        body["voice_settings"] = {"guidance_scale": gs}
    r = requests.post(BASE + "/v1/text-to-speech/" + VOICE, headers=H,
                      json=body, timeout=180)
    if r.status_code != 200:
        print("%-26s HTTP %s %s" % (name, r.status_code, (r.text or "")[:120]))
        continue
    p = OUT / (name + ".mp3")
    p.write_bytes(r.content)
    print("%-26s %5.0f KB  %s" % (name, len(r.content) / 1024.0, p.name))

r = requests.get(BASE + "/v1/balance", headers=H, timeout=20)
print()
print("余额:", r.json().get("balance"))
