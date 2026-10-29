# -*- coding: utf-8 -*-
"""触发一次图片处理以激活图片 AES key，然后立刻扫内存。

做法：让绯栀给自己的「文件传输助手」发一张本地图。
微信发送时必须读图 → 编码 → 写缓存，从而把图片 AES key 载入内存。
同时这条消息会在 inbox 里留下一条 type=3 记录，可用于端到端校验。
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

import bridge  # noqa: E402

IMG = Path(sys.argv[1] if len(sys.argv) > 1
           else r"<PROJECT_ROOT>\feizhi_pc\images\gen_9f816f698803f168.jpg")


def main() -> int:
    print("发送图片:", IMG, IMG.is_file(), flush=True)
    b = bridge.HookBridge()
    print("worker_healthy:", b.worker_healthy(), "ctx_age:",
          b.ctx_age_sec(), flush=True)
    ok = b.send_image("filehelper", str(IMG), timeout=45)
    print("send_image ->", ok, flush=True)
    if not ok:
        return 1
    for wait in (3, 5, 8):
        time.sleep(wait)
        print("  等待 %ds 后扫 key..." % wait, flush=True)
        import img_dat as M
        key = M.extract_aes_key(force=True)
        print("  AES key:", key, flush=True)
        if key:
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
