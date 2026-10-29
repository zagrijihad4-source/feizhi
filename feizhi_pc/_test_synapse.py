"""对比测试 synapse 线路：同一个 prompt，量耗时与产物形态。

不动 image_config.json（provider 仍是 sanbao），直接调备用线路函数，
并关掉熔断记账（affect_breaker=False），免得影响正在跑的服务。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import imagegen  # noqa: E402

PROMPT = "绯栀坐在宿舍书桌前改海报，深夜台灯暖黄光，桌上摊着靛蓝色的画稿，侧脸低头，写实摄影"
OUT = ROOT / "eval" / "_synapse_test.png"

cfg = imagegen.load_config()
t0 = time.time()
p = imagegen._synapse_generate(PROMPT, cfg, "16:9", 300.0, OUT, affect_breaker=False)
el = time.time() - t0

if not p:
    print("失败  %.1fs" % el)
    sys.exit(1)
print("成功  %.1f 秒  %s  %.0f KB" % (el, p.name, p.stat().st_size / 1024.0))
print("ABS %s" % p)
