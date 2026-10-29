"""探测 synapse 线路到底挂在哪：是 key 失效，还是尺寸参数变了。

上一次用 size=1536x1024 返回 HTTP 400，错误体里它自己建议「832 × 1248，比例 2:3」。
HTTP 400 意味着 key 大概率还有效（否则会是 401/403），所以先按它建议的尺寸再试一次，
失败则打印完整错误体（用 UTF-8 正确解码，不像 PowerShell 那样乱码）。
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import imagegen  # noqa: E402

PROMPT = "绯栀坐在宿舍书桌前改海报，深夜台灯暖黄光，桌上摊着靛蓝色的画稿，侧脸低头，写实摄影"
OUT = ROOT / "eval" / "_synapse_test2.png"

cfg = imagegen.load_config()
cfg.setdefault("synapse", {})["size"] = "832x1248"

t0 = time.time()
p = imagegen._synapse_generate(PROMPT, cfg, "16:9", 300.0, OUT, affect_breaker=False)
print("elapsed %.1fs" % (time.time() - t0))
if p:
    print("成功 %s %.0f KB" % (p.name, p.stat().st_size / 1024.0))
    print("ABS %s" % p)
    sys.exit(0)

# 再打一次原始请求，把完整错误体按 UTF-8 解出来
import requests  # noqa: E402

sc = cfg["synapse"]
body = {"model": sc.get("model", "gpt-image-2"), "prompt": PROMPT,
        "n": 1, "size": "832x1248"}
r = requests.post(str(sc["baseURL"]).rstrip("/") + "/images/generations",
                  headers={"Authorization": "Bearer " + str(sc["apiKey"]),
                           "Content-Type": "application/json"},
                  json=body, timeout=120)
print("HTTP", r.status_code)
text = r.content.decode("utf-8", "replace")
print(text[:1200])
