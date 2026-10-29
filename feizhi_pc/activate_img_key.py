# -*- coding: utf-8 -*-
"""等一张图 —— 把图片 AES key 抓下来并缓存（一次性，之后永久可用）。

背景：微信 4.x 收到的图片缓存在 `.dat` 里，结构是
      `[AES段][明文段][XOR段]`，其中 AES 段的 key 只存在于微信进程内存，
    而且**只有微信真的显示过图片时才会载入**。

所以激活流程是：
    1. 运行本脚本（它会一直轻量轮询）
    2. 在微信里**看一张图**（收到别人发的图，或点开任意一张图片）
    3. 脚本一旦发现 key 就写入 state/image_key.json 并退出

之后 img_dat / autoreply 就能直接解密任意图片缓存，不用再跑这个。

用法:
    python activate_img_key.py [最长等待秒数，默认 600]
"""
from __future__ import annotations

import logging
import sys
import time

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import img_dat as M  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    print("=== 图片 AES key 激活 ===", flush=True)
    print("现在请去微信里【看一眼任意一张图片】：", flush=True)
    print("  · 让别人给你发一张图（收到即会显示缩略图），或", flush=True)
    print("  · 点开聊天里任意一张历史图片", flush=True)
    print("脚本会一直在后台盯着，拿到 key 自动保存并退出。\n", flush=True)

    t0 = time.time()
    attempt = 0
    while time.time() - t0 < limit:
        attempt += 1
        key = M.extract_aes_key(force=True)
        if key:
            print("\n*** 拿到 key: %s ***" % key.hex(), flush=True)
            # 立刻验证能否解开现有缓存
            ok = 0
            for p in sorted(M.ATTACH.rglob("*.dat"))[:40]:
                got = M.decrypt_dat(p, key)
                if got:
                    ok += 1
            print("用这把 key 成功解密 %d 张缓存图片" % ok, flush=True)
            print("已写入 %s" % M.KEY_FILE, flush=True)
            return 0
        print("  第 %d 次扫描：还没有 key（%.0fs）…" % (attempt, time.time() - t0),
              flush=True)
        time.sleep(6)
    print("\n超时仍未拿到 key。确认微信里确实显示过图片后再试一次。", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
