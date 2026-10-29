# -*- coding: utf-8 -*-
"""连测 3 次语音发送，看 calls=0 是否成串出现。

用途：判定「间歇」还是「持续性」。
  连败 3 次 → 当前有持续性问题（设备占用/微信状态）
  失败 1 次后成功 → 一次性竞争，重试策略本身对
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> int:
    import voice

    sender = voice.VoiceSender()
    if not sender._ensure():
        print("hook 不可用")
        return 2
    sender.open_recent_chat()
    time.sleep(0.6)

    pcm = Path(__file__).parent / "state" / "_probe.pcm"
    if not pcm.exists():
        pcm.write_bytes(b"\x00\x00" * 16000)

    results = []
    for i in range(3):
        ok = sender._say_once(pcm, max_hold=10)
        results.append(ok)
        print("第 %d 次: %s" % (i + 1, "成功" if ok else "失败 calls=0" if not ok else ""),
              flush=True)
        time.sleep(1.2)
    sender.close()
    print("结果:", results)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
