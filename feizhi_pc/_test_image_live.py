"""实测生图：走真实链路（三宝主 + synapse 备），量耗时与产物。

用全新 prompt 以免命中缓存，否则测的只是本地文件。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import imagegen  # noqa: E402

PROMPT = "绯栀坐在宿舍书桌前改海报，深夜台灯暖黄光，桌上摊着靛蓝色的画稿，侧脸低头，写实摄影"

t0 = time.time()
try:
    p = imagegen.generate(PROMPT)
except Exception as e:  # noqa: BLE001
    print("失败（异常）：%r" % (e,))
    sys.exit(1)

el = time.time() - t0
if not p:
    print("失败（返回 None，耗时 %.1fs）" % el)
    sys.exit(1)
print("成功  %.1f 秒  %s  %.0f KB" % (el, p.name, p.stat().st_size / 1024.0))
print("ABS %s" % p)
