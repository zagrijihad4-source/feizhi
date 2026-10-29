"""把 feizhi_B_sample.wav 克隆成 breeze 音色。

三步：create-clone-preview -> stream 试听 -> save 成私有音色。
保存会消耗一个 voice slot，所以先落试听文件让人听过再决定是否 save。

参考样本要求（官方）：单样本 / 单人 / 无背景音乐 / mp3 或 wav / ≥3 秒 / ≤5 MB。
Breeze 只分析前 60 秒，并在最后一个完整句子处截取最多 30 秒，归一化到 -18 LUFS。
"""
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
SAMPLE = Path(r"<PROJECT_ROOT>\feizhi_pc\voice\feizhi_B_sample.wav")
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

print("样本: %s  %.1f 秒  %.2f MB"
      % (SAMPLE.name, SAMPLE.stat().st_size / 32000.0, SAMPLE.stat().st_size / 1048576.0))

# 1) 创建克隆预览
with SAMPLE.open("rb") as fh:
    r = requests.post(BASE + "/v1/voice-previews/clone", headers=H,
                      data={"name": "Feizhi", "reference_language_code": "zh",
                            "remove_background_noise": "true"},
                      files={"files": (SAMPLE.name, fh, "audio/wav")},
                      timeout=300)
print("create: HTTP %s" % r.status_code)
if r.status_code != 200:
    print((r.text or "")[:500])
    sys.exit(1)

preview = r.json()
print("响应:", {k: v for k, v in preview.items() if k != "audio_base64"})
gid = preview.get("generated_voice_id") or preview.get("generatedVoiceId")
if not gid:
    sys.exit("没有 generated_voice_id")

# 2) 试听（这个是 Breeze 用该音色念它自动生成的预览台词，不是我们的文本）
r2 = requests.get(BASE + "/v1/voice-previews/%s/stream" % gid, headers=H, timeout=300)
print("stream: HTTP %s  %d 字节" % (r2.status_code, len(r2.content)))
if r2.status_code == 200 and len(r2.content) > 1000:
    p = OUT / "H-克隆预览-绯栀.mp3"
    p.write_bytes(r2.content)
    print("试听已存:", p)

print()
print("GENERATED_VOICE_ID =", gid)
print("（确认试听没问题后，用 _save_voice.py 保存成长期 voice_id）")
