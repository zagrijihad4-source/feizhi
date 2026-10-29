# -*- coding: utf-8 -*-
"""图片链路冒烟测试：key 状态 → 缓存定位 → 解密 → 识别。

跑法:
    python _test_vision.py                 # 全流程自检
    python _test_vision.py <图片文件>       # 只测视觉识别

预期结果（key 已激活时）：
    [1] 密钥  ✅ / ❌
    [2] 定位  找到 N 个候选 dat
    [3] 解密  成功解出 M 张，打印尺寸与格式
    [4] 识别  给出中文描述
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import img_dat  # noqa: E402
import vision  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        p = Path(args[0])
        print("[*] 只测识别:", p)
        print("[4] 识别 ->", vision.describe_file(p) or "(失败)")
        return 0

    print("[1] 密钥:", end=" ")
    key = img_dat.extract_aes_key()
    if not key:
        print("❌ 未就绪 —— 先在电脑端微信里显示一张图片（手机发一张给绯栀最省事），"
              "再跑 activate_img_key.py")
        return 1
    print("✅", key.hex())

    print("[2] 缓存目录:", img_dat.ATTACH)
    dats = sorted(img_dat.ATTACH.rglob("*.dat"))
    print("    共 %d 个 dat" % len(dats))
    if not dats:
        return 1

    print("[3] 解密抽样:")
    ok = 0
    first = None
    for p in dats[:24]:
        got = img_dat.decrypt_dat(p, key)
        if not got:
            continue
        plain, ext = got
        ok += 1
        print("    %-46s %-5s %8d B" % (p.name[:46], ext, len(plain)))
        # 视觉模型只吃 jpg/png/webp/gif；wxgf(HEVC) 那档要跳过
        if first is None and ext in ("jpg", "png", "webp", "gif"):
            first = plain
    print("    成功 %d / %d" % (ok, min(24, len(dats))))
    if not first:
        print("    ❌ 没解出可用格式的图片")
        return 1

    print("[4] 识别第一张:")
    print("   ", vision.describe_bytes(first) or "(识别失败)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
