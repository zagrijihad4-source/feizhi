"""重试克隆：去掉 remove_background_noise（该参数会在降噪吃掉有效人声时
再走一遍原音频，可能正是 503 的来源），并做有限次退避重试。

文档原话：Service errors remain retryable and are not audio-quality verdicts.
所以 503 不代表样本不能用。
"""
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
SAMPLE = Path(r"<PROJECT_ROOT>\feizhi_pc\voice\feizhi_B_sample.wav")
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

for attempt in range(3):
    if attempt:
        wait = 8 * attempt
        print("等待 %d 秒后重试…" % wait)
        time.sleep(wait)
    with SAMPLE.open("rb") as fh:
        r = requests.post(BASE + "/v1/voice-previews/clone", headers=H,
                          data={"name": "Feizhi", "reference_language_code": "zh"},
                          files={"files": (SAMPLE.name, fh, "audio/wav")},
                          timeout=300)
    print("第 %d 次：HTTP %s" % (attempt + 1, r.status_code))
    if r.status_code == 200:
        break
    print("  ", (r.text or "")[:240])
else:
    sys.exit("三次都失败")

preview = r.json()
gid = preview.get("generated_voice_id") or preview.get("generatedVoiceId")
print("响应字段:", sorted(preview.keys()))
print("GENERATED_VOICE_ID =", gid, " name=", preview.get("name"),
      " language=", preview.get("language_code") or preview.get("language"))
if preview.get("transcript"):
    print("参考转录:", str(preview["transcript"])[:120])

if gid:
    r2 = requests.get(BASE + "/v1/voice-previews/%s/stream" % gid, headers=H, timeout=300)
    print("stream: HTTP %s  %d 字节" % (r2.status_code, len(r2.content)))
    if r2.status_code == 200 and len(r2.content) > 1000:
        p = OUT / "H-克隆预览-绯栀.mp3"
        p.write_bytes(r2.content)
        print("试听已存:", p)
