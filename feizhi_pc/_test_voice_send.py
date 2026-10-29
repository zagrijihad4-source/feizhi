"""实测语音发送链路，确认 calls 是否终于不为 0。

会真的往微信发一条语音（会短暂抢前台）。
"""
import logging
import sys
import time

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import voice  # noqa: E402

t0 = time.time()
ok = voice.say("这条是测试呀，听到就说明修好了", "温柔")
print("=" * 50)
print("ok=%s  用时 %.1f 秒" % (ok, time.time() - t0))
