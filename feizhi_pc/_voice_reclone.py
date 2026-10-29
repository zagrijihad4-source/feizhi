"""用音音子真实录音重新克隆，替换掉 voicedesign 合成样本。

现用 feizhi_B_sample.wav 是 voicedesign 生成的「冷清慵懒」，F0 sd 55.2。
真实分离人声 yy_12_vocal.wav F0 sd 78.6、动态 26.2，起伏明显更好。
克隆后不立即替换生产配置，先按 preview 试听对比。
"""
import shutil
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
SRC = Path(r"<PROJECT_ROOT>\sing\source\sep_test\yy_12_vocal.wav")
WORK = Path(r"<PROJECT_ROOT>\feizhi_pc\voice")
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

# 复制到工作区，避免直接引用素材目录（素材可能被后续清理）
sample = WORK / "feizhi_real_yy12.wav"
shutil.copy2(SRC, sample)
print("样本: %s  %.2f MB" % (sample.name, sample.stat().st_size / 1048576.0))

for attempt in range(3):
    if attempt:
        time.sleep(6 * attempt)
    with sample.open("rb") as fh:
        r = requests.post(BASE + "/v1/voice-previews/clone", headers=H,
                          data={"name": "FeizhiReal", "reference_language_code": "zh"},
                          files={"files": (sample.name, fh, "audio/wav")},
                          timeout=300)
    print("clone 第 %d 次: HTTP %s" % (attempt + 1, r.status_code))
    if r.status_code == 200:
        break
    print("  ", (r.text or "")[:200])
else:
    sys.exit("clone 失败")

gid = r.json().get("generated_voice_id")
print("generated_voice_id =", gid)

r2 = requests.get(BASE + "/v1/voice-previews/%s/stream" % gid, headers=H, timeout=300)
print("stream: HTTP %s  %d 字节" % (r2.status_code, len(r2.content)))
if r2.status_code == 200:
    p = OUT / "AA-克隆预览-真实样本.mp3"
    p.write_bytes(r2.content)
    print("试听:", p.name)

print()
print("下一步：听完满意就 save 成 voice_id（替换 voc_uj5qvdgfhuhz）")
