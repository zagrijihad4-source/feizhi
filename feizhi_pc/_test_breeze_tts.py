"""列出 breezeblue 可用音色、展开参数 schema，并做一次真实中文合成。

合成结果存到桌面 `语音诊断\\`，和 mimo 的样本放一起，方便直接对比。
"""
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}
OUT = Path(r"C:\Users\api62\Desktop\语音诊断")

# 1) 音色列表
r = requests.get(BASE + "/v1/voices", headers=H, timeout=20)
print("=== /v1/voices  HTTP %s ===" % r.status_code)
try:
    data = r.json()
    items = data if isinstance(data, list) else (data.get("voices") or data.get("items") or [])
    print("共 %d 个音色" % len(items))
    for v in items[:12]:
        vid = v.get("voice_id") or v.get("id")
        name = v.get("name") or ""
        labels = v.get("labels") or {}
        lang = labels.get("language") or v.get("language") or ""
        print("  %-28s %-18s %s" % (vid, name, lang))
    if len(items) > 12:
        print("  ...（还有 %d 个）" % (len(items) - 12))
    first_id = (items[0].get("voice_id") or items[0].get("id")) if items else None
except Exception as e:  # noqa: BLE001
    print("解析失败", e, (r.text or "")[:200])
    first_id = None

# 2) voice_settings schema
spec = requests.get(BASE + "/openapi.json", headers=H, timeout=20).json()
schemas = (spec.get("components") or {}).get("schemas") or {}
print()
print("=== voice_settings ===")
for name, s in schemas.items():
    if "voice" in name.lower() and "setting" in name.lower():
        print(" %s:" % name)
        for k, v in (s.get("properties") or {}).items():
            print("   %-18s %s  默认=%s" % (k, v.get("type") or "", v.get("default")))

# 3) 真实合成
TEXT = "你今天到底几点睡的，眼睛都睁不开了吧，还嘴硬说没困。"
INSTR = ("用19岁女孩的口气说，嘴硬心软：前半句带着点埋怨，语速偏快；"
         "后半句软下来，尾音往下掉，藏一点心疼。不要念稿感。")

if first_id:
    body = {
        "text": TEXT,
        "model_id": "breeze-tts-2",
        "language_code": "zh",
        "instructions": INSTR,
    }
    r2 = requests.post(BASE + "/v1/text-to-speech/" + str(first_id),
                       headers={**H, "Content-Type": "application/json"},
                       json=body, timeout=180)
    print()
    print("=== 合成 HTTP %s  voice=%s ===" % (r2.status_code, first_id))
    ctype = r2.headers.get("Content-Type", "")
    print("Content-Type:", ctype, " 字节:", len(r2.content))
    if r2.status_code == 200 and ("audio" in ctype or r2.content[:4] in (b"RIFF", b"ID3\x03")):
        ext = ".mp3" if "mpeg" in ctype or "mp3" in ctype else ".wav"
        p = OUT / ("D-breeze-中文" + ext)
        p.write_bytes(r2.content)
        print("已保存:", p)
    elif r2.status_code == 200:
        try:
            print(json.dumps(r2.json(), ensure_ascii=False)[:400])
        except Exception:  # noqa: BLE001
            print("非音频响应:", r2.content[:200])
    else:
        print((r2.text or "")[:400])
