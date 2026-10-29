"""用 MiMo 生成的"她的声音"做 breeze 克隆，再对比。

这是补上的一步：之前用的是原料 feizhi_B_sample.wav，不是用户认的那把嗓子。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
SAMPLE = ROOT / "voice" / "feizhi_mimo_reference.wav"
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

print("样本 %.2f MB" % (SAMPLE.stat().st_size / 1048576.0))

gid = None
for attempt in range(3):
    if attempt:
        time.sleep(6 * attempt)
    with SAMPLE.open("rb") as fh:
        r = requests.post(BASE + "/v1/voice-previews/clone", headers=H,
                          data={"name": "FeizhiMiMo", "reference_language_code": "zh"},
                          files={"files": (SAMPLE.name, fh, "audio/wav")},
                          timeout=300)
    print("clone 第 %d 次: HTTP %s" % (attempt + 1, r.status_code))
    if r.status_code == 200:
        gid = r.json().get("generated_voice_id")
        break
    print("  ", (r.text or "")[:200])
if not gid:
    sys.exit("克隆失败")

r2 = requests.get(BASE + "/v1/voice-previews/%s/stream" % gid, headers=H, timeout=300)
if r2.status_code == 200:
    (OUT / "CC-克隆预览-MiMo参考.mp3").write_bytes(r2.content)
    print("预览已存（%d 字节）" % len(r2.content))

Hj = {**H, "Content-Type": "application/json"}
r3 = requests.post(BASE + "/v1/voice-previews/%s/save" % gid, headers=Hj,
                   json={"voice_name": "FeizhiMiMo", "language_code": "zh"}, timeout=180)
vid = r3.json().get("voice_id") if r3.status_code == 200 else None
print("save HTTP %s  voice_id = %s" % (r3.status_code, vid))
if not vid:
    sys.exit(1)

import tts  # noqa: E402
import voice  # noqa: E402

TEXT = "你今天几点睡的呀，我看你都困成这样了。"
STYLE = voice.style_for("温柔")
IDS = [("旧-原料克隆", "voc_uj5qvdgfhuhz"),
       ("真音-唱歌克隆", "voc_z4npxsc7ch8m"),
       ("新-MiMo参考克隆", vid)]

for tag, v in IDS:
    wav = tts._breeze_synthesize(TEXT, STYLE, v, None, 90, guidance=8)
    (OUT / ("DD-%s.wav" % tag)).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_dd_%s.pcm" % tag.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    print("%-16s %5.0f KB" % (tag, len(wav) / 1024.0))

json.dump({"voice_id": vid, "voice_name": "FeizhiMiMo", "language_code": "zh",
           "source_sample": "voice/feizhi_mimo_reference.wav",
           "note": "MiMo 合成声音 → breeze 克隆；这才是用户认的那把嗓子"},
          open(str(ROOT / "breeze_voice_mimo.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print()
print("MIMO_VOICE_ID =", vid)
