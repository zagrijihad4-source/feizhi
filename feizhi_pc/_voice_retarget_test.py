# -*- coding: utf-8 -*-
"""验证 pack 提交点的收件人改写是否真的生效。

手法：把目标设成一个**不存在的 wxid**（长度和真的一样，20 字符），发一条语音。
  - 如果日志出现 `voice retarget: wxid_99r5... -> wxid_fake...`，说明改写成功
    （这条语音随后会因为收件人不存在而发不出去，无害）
  - 如果连 retarget 日志都没有，说明 hook 没挂上或类型码判断错了

这一步不需要动用户的微信会话，可以先证明机制通。
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import voice  # noqa: E402

FAKE = "wxid_fei_retarget_test"      # 20 字符，和真 wxid 等长
REAL = "<WXID_FRIEND_A>"
PCM = ROOT / "tmp" / "_retarget_probe.pcm"


def main() -> int:
    import tts

    if not PCM.exists():
        print("合成一句短的 PCM…")
        wav = tts._breeze_synthesize("测试改写", None, None, None, 90)
        tts.to_wechat_pcm(wav, PCM)
    print("PCM:", PCM, PCM.stat().st_size, "bytes")

    sender = voice.VoiceSender()
    if not sender._ensure():
        print("hook 不可用")
        return 2
    print("hook 就绪, hwnd =", sender._hwnd)

    print("\n[1] 设目标 =", FAKE)
    print("    setTarget ->", sender._ex.setTarget(FAKE))
    print("    getTarget ->", sender._ex.getTarget())

    print("\n[2] 发一条（收件人会被改成上面的假 wxid）")
    ok = sender._say_once(PCM, max_hold=12.0)
    print("    _say_once ->", ok)

    print("\n[3] 清空目标")
    print("    clearTarget ->", repr(sender._ex.clearTarget()))
    print("    getTarget ->", repr(sender._ex.getTarget()))

    sender.close()
    print("\n看日志里有没有 'voice retarget:' 那一行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
