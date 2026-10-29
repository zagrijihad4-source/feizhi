"""解码抖音 RENDER_DATA，抽出用户 sec_uid、昵称和视频 aweme_id。"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

p = Path(sys.argv[1])
raw = p.read_text(encoding="utf-8", errors="replace").strip()
print("原始长度", len(raw))

dec = urllib.parse.unquote(raw)
print("解码后长度", len(dec))

try:
    data = json.loads(dec)
    print("JSON 解析成功，顶层键:", list(data.keys())[:10])
except Exception as exc:  # noqa: BLE001
    print("JSON 解析失败:", exc)
    data = None

# 直接在文本里搜关键 id
sec_uids = sorted(set(re.findall(r"MS4wLjABAAAA[A-Za-z0-9_\-]{20,}", dec)))
aweme_ids = sorted(set(re.findall(r'"aweme_id"\s*:\s*"(\d{15,})"', dec)))
ids2 = sorted(set(re.findall(r"/video/(\d{15,})", dec)))
nicknames = sorted(set(re.findall(r'"nickname"\s*:\s*"([^"]{1,20})"', dec)))

print("\nsec_uid 候选 (%d):" % len(sec_uids))
for s in sec_uids[:10]:
    print("  ", s)
print("\naweme_id (%d):" % len(aweme_ids))
for a in aweme_ids[:20]:
    print("  ", a)
print("\n/video/ 链接里的 id (%d):" % len(ids2))
for a in ids2[:20]:
    print("  ", a)
print("\nnickname 候选:", nicknames[:20])

# 如果解析成 JSON，深挖 user / aweme 结构
if isinstance(data, dict):
    def walk(o, path=""):
        if isinstance(o, dict):
            if "sec_uid" in o or "aweme_id" in o:
                keys = {k: o[k] for k in ("sec_uid", "uid", "nickname", "unique_id",
                                          "aweme_id", "desc", "duration")
                        if k in o}
                if keys:
                    print("  [node]", path, keys)
            for k, v in o.items():
                walk(v, path + "/" + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o[:40]):
                walk(v, path + "[%d]" % i)

    print("\n=== 结构里带 sec_uid / aweme_id 的节点 ===")
    walk(data)
