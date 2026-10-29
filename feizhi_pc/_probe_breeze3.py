"""找出 breezeblue 的 TTS 合成入口与请求 schema，并查余额。"""
import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"
H = {"Authorization": "Bearer " + KEY}

spec = requests.get(BASE + "/openapi.json", headers=H, timeout=20).json()
paths = spec.get("paths") or {}

print("=== 合成相关路由 ===")
KEYWORDS = ("tts", "speech", "audio", "generation", "voice", "clone")
hits = []
for p, ops in sorted(paths.items()):
    low = p.lower()
    if any(k in low for k in KEYWORDS):
        for method, op in ops.items():
            if method.lower() in ("get", "post"):
                hits.append((method.upper(), p, op))
                print("  %-6s %-52s %s" % (method.upper(), p,
                                           (op.get("summary") or "")[:40]))

print()
print("=== 余额 ===")
try:
    r = requests.get(BASE + "/v1/balance", headers=H, timeout=20)
    print(" ", r.status_code, (r.text or "")[:300])
except Exception as e:  # noqa: BLE001
    print(" 失败", e)

print()
print("=== 合成入口的请求 schema ===")
# 优先看 POST 且路径里带 tts / speech / generation 的
for method, p, op in hits:
    if method != "POST":
        continue
    if not any(k in p.lower() for k in ("tts", "speech", "generation")):
        continue
    body = (op.get("requestBody") or {}).get("content") or {}
    for ctype, c in body.items():
        schema = c.get("schema") or {}
        ref = schema.get("$ref")
        if ref:
            name = ref.split("/")[-1]
            schema = (spec.get("components", {}).get("schemas", {}) or {}).get(name, {})
        print("  %s  (%s)" % (p, ctype))
        props = schema.get("properties") or {}
        req = set(schema.get("required") or [])
        for k, v in props.items():
            t = v.get("type") or v.get("anyOf") or v.get("$ref") or ""
            enum = v.get("enum")
            print("     %-18s %-12s %s%s"
                  % (k, str(t)[:12],
                     "必填 " if k in req else "",
                     ("可选值=" + str(enum)) if enum else (v.get("default") if v.get("default") is not None else "")))
        print()
