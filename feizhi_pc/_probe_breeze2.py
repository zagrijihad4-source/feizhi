"""拿 breezeblue 的完整模型列表和端点定义。

404 的响应体是 FastAPI 风格（{"detail":"Not Found"}），所以先试 /openapi.json，
一次把全部路由和请求 schema 拿下来，比瞎猜端点快。
"""
import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}

r = requests.get(BASE + "/v1/models", headers=H, timeout=20)
models = r.json()
print("=== 模型（%d 个）===" % len(models))
for m in models:
    langs = ",".join(l.get("language_id", "") for l in (m.get("languages") or []))
    print("  %-24s %-22s [%s]" % (m.get("model_id"), m.get("name"), langs))
    if m.get("description"):
        print("      %s" % m["description"])

print()
print("=== openapi ===")
try:
    doc = requests.get(BASE + "/openapi.json", headers=H, timeout=20)
    print("HTTP", doc.status_code)
    if doc.status_code == 200:
        spec = doc.json()
        paths = spec.get("paths") or {}
        for p, ops in sorted(paths.items()):
            for method in ops:
                if method.lower() in ("get", "post", "put", "delete"):
                    print("  %-6s %s" % (method.upper(), p))
    else:
        print((doc.text or "")[:300])
except Exception as e:  # noqa: BLE001
    print("失败 %r" % (e,))
