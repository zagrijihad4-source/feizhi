"""sing 模块 dry-run：只取段不发送。

发送会真的操作微信窗口，测试阶段不做。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import sing  # noqa: E402

print("曲库（按修改时间倒序）：")
for t in sing.tracks():
    print("  %-26s 《%s》  %5.1f 秒" % (t["file"], t["title"], t["sec"]))
print()
print("给 prompt 的清单：", sing.catalog_text())
print()

for name in ("樱花树下的约定", "沦陷", "潮汐", "这首歌不存在"):
    p = sing.make_pcm(name)
    if p is None:
        print("%-10s -> 未找到" % name)
        continue
    size = p.stat().st_size
    print("%-10s -> %-22s %5.1f 秒  %d 字节" % (name, p.name, size / 32000.0, size))
    p.unlink(missing_ok=True)
