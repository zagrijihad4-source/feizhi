"""找出 breeze 指定输出格式的正确方式：query 还是 Accept 头。

body 里放 output_format 会 422（extra_forbidden），说明它不在请求体里。
SDK 的 convert(..., output_format=...) 可能把它落成 query 参数。
"""
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
VOICE = "voc_uj5qvdgfhuhz"
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

TEXT = "你今天到底几点睡的，[叹气] 还嘴硬说没困。"
INSTR = "用19岁女孩的口气，带点埋怨，后半句软下来。"
BODY = {"text": TEXT, "model_id": "breeze-tts-2", "language_code": "zh",
        "instructions": INSTR}

CASES = [
    ("query wav", BASE + "/v1/text-to-speech/%s?output_format=wav" % VOICE, H),
    ("Accept wav", BASE + "/v1/text-to-speech/" + VOICE, {**H, "Accept": "audio/wav"}),
    ("默认", BASE + "/v1/text-to-speech/" + VOICE, H),
]

for name, url, headers in CASES:
    r = requests.post(url, headers=headers, json=BODY, timeout=180)
    ctype = r.headers.get("Content-Type", "")
    print("%-12s HTTP %s  %-18s %7d 字节  头=%r"
          % (name, r.status_code, ctype, len(r.content),
             r.content[:4] if r.status_code == 200 else b""))
    if r.status_code == 200 and ctype.startswith("audio"):
        ext = "wav" if "wav" in ctype else "mp3"
        p = OUT / ("J-格式测试-%s.%s" % (name.replace(" ", ""), ext))
        p.write_bytes(r.content)
    elif r.status_code != 200:
        print("   ", (r.text or "")[:180])
