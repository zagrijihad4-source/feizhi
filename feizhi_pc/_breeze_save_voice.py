"""把克隆预览保存成可复用的私有音色，拿到长期 voice_id。"""
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
GID = "gvi_xtvmss2zjupm"

r = requests.post(BASE + "/v1/voice-previews/%s/save" % GID,
                  headers={**H, "Content-Type": "application/json"},
                  json={"voice_name": "Feizhi", "language_code": "zh"},
                  timeout=180)
print("HTTP", r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:800])

if r.status_code == 200:
    vid = r.json().get("voice_id")
    print()
    print("VOICE_ID =", vid)
    # 落一份配置片段，供 tts.py 读
    p = Path(r"<PROJECT_ROOT>\feizhi_pc\breeze_voice.json")
    p.write_text(json.dumps({"voice_id": vid, "voice_name": "Feizhi",
                             "language_code": "zh",
                             "clone_preview": GID}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print("已写入", p)
