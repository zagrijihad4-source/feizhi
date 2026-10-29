"""探测 breezeblue 的 API 入口与连通性。

先解决三个问题：
  1. 域名解不解析得了（国内直连的前提）；
  2. 哪个 base URL 是真的 API 入口（官网 / 文档 / api 子域）；
  3. key 有没有效（401 vs 200）。

不打印完整 key。
"""
import json
import socket
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
MASK = KEY[:8] + "..." + KEY[-4:]

HOSTS = [
    "breezeblue.ai",
    "api.breezeblue.ai",
    "www.breezeblue.ai",
    "breezeblue.com",
    "api.breezeblue.com",
]

print("=== DNS ===")
for h in HOSTS:
    try:
        ip = socket.gethostbyname(h)
        print("  %-22s -> %s" % (h, ip))
    except Exception as e:  # noqa: BLE001
        print("  %-22s -> 解析失败（%s）" % (h, type(e).__name__))

print()
print("=== 候选端点（key=%s）===" % MASK)
CANDIDATES = [
    ("https://api.breezeblue.ai/v1/models", True),
    ("https://api.breezeblue.ai/models", True),
    ("https://breezeblue.ai/api/v1/models", True),
    ("https://api.breezeblue.ai/v1/audio/speech", True),
    ("https://breezeblue.ai/v1/models", True),
]

for url, auth in CANDIDATES:
    h = {"Authorization": "Bearer " + KEY} if auth else {}
    try:
        r = requests.get(url, headers=h, timeout=15, allow_redirects=False)
        body = (r.text or "")[:200].replace("\n", " ")
        print("  %-45s %s  %s" % (url, r.status_code, body))
    except Exception as e:  # noqa: BLE001
        print("  %-45s 失败 %s" % (url, type(e).__name__))
