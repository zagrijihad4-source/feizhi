import io
from pathlib import Path

p = Path("声音歌唱进度报告.md")
s = io.open(p, encoding="utf-8").read()

head = "# 音音子 RVC 声音克隆 · 歌唱进度报告"
assert s.startswith(head)

block = """
---

## ★ 模型定版（2026-10-29 追加）

**从此统一使用 `yinyin10.pth`**，`rvc_cover.py` 的默认模型已改。其余模型**全部保留**，报告对比还要用。

| 模型 | 时间 | 状态 |
| --- | --- | --- |
| yinyin / yinyin2 / yinyin3 / yinyin4 / yinyin5 | 2026-10-21 | 历史实验，留档 |
| yinyin6 | 2026-10-22 01:01 | 历史实验，留档 |
| yinyin7 | 2026-10-22 14:59 | `weights_backup/yinyin7_FAILED_20261022.pth` 标注为失败 |
| **yinyin10** | **2026-10-24 00:02** | **定版，对外交付一律用它** |

### 两条必须记住的参数

**1) `--index-rate 0`，不要用 0.95**

`deliver_y6.py` / `deliver_y7.py` 交付时用的都是 `--index-rate 0`。索引（faiss）会把内容特征往检索集上拽：音色听起来像"一批样本的平均"，不是她，而且会换掉音素导致唱错字。`rvc_cover.py` 的注释也写着「0 = 不用索引，内容特征 100% 忠实原唱」。

**2) `--protect 0.5`**

保护原唱清辅音的比例，控制咬字清晰度。

### 分块分离不能用 process()

`separate_any.py` 底层的 `VocalSeparator.process()` 在 ~22 秒以上的输入上会**卡死**（10 秒窗口只要 5.8 秒）。`separate_chunked.py` 的注释里就写着这一点。4 分半的整首歌必须走 `separate_chunked.py`（自己分 10 秒窗口、1 秒重叠），实测 260 秒的歌 110 秒跑完。

### 一条完整产线的实测耗时（RTX 4060 Laptop）

以《雨爱》（260 秒）为例：

```
分离  separate_chunked.py   29 个窗口        110 秒
转音  rvc_cover.py          yinyin10 / rate 0 / protect .5    35 秒
混音  mix_cover.py          人声 1.0 + 伴奏 0.8              4 秒
```

### 踩过的坑：用错模型

第一次做《雨爱》时按旧记忆用了 `yinyin5.pth` + `index-rate 0.95`，用户一听就说音色不对。换回 `yinyin10` + `index-rate 0` 才对。**记忆里的"默认 protect .5 + index .95"是调音色亮度时的实验结论，不是交付参数。**

"""

s = s.replace(head, head + block, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("文档已更新：%s" % p)
