# TASK_LOG · 看图与联网（图片识别 + 联网搜索）

日期：2026-10-25
涉及模块：`feizhi_pc/vision.py`（新）、`img_dat.py`（新）、`search.py`（重写加固）、
`autoreply.py`（接线）、`persona.py`（VISION_STYLE）

目标：让绯栀**能看见他发的图**、**能自己联网查事**。

---

## 一、结论先说

| 能力 | 状态 | 依赖 |
|---|---|---|
| 联网搜索 | ✅ 可用 | DeepSeek Search API（Bing 爬虫兜底） |
| 图片识别（视觉） | ✅ 可用 | `deepseek-flash`（同 key，claude 兜底） |
| 图片解密（收到图的像素） | ✅ 可用 | 图片 AES key（**从磁盘派生，不用碰进程**） |

图片解密引擎已逐字节验证（§三），密钥由账号目录名 + uin 派生（§四），
不依赖微信是否显示过图片。历史 4 条图片消息里能拿到缓存的那条已实测跑通，
完整读出截图中的对话文字。

---

## 二、关键事实：收到的图片，XML 里没有本地路径

inbox 里 `type=3` 的 `content` 只有加密的 CDN 指针：

```xml
<img aeskey="d575f0ea…" encryver="1"
     cdnthumburl="305f0201…" cdnthumblength="18016"
     cdnthumbheight="283" cdnthumbwidth="504"
     length="270384" md5="333d8334843db36939e696368df925b1" … />
```

`cdnthumburl` 不是 URL，是微信内部加密的下载指针；`aeskey` 是**这张图自己的**
CDN 密钥，跟本地缓存无关。所以"收图 → 视觉"不能靠解析 XML 拿到文件。

另外确认：hook DLL 的能力边界只有**发送**方向（`send_image.c`），
接收侧只把消息对象里的 content 字符串 dump 出来（`wx_bridge_offsets.h`
里 `WX_MSG_CONTENT_OFF 0x160`）。接收方向没有任何图片像素能力。

---

## 三、微信 4.x 图片缓存格式（V2）—— 逐字节验证过

缓存位置：

```
<账号根>\msg\attach\<md5(对方wxid)>\<YYYY-MM>\Img\<id>{_t,_h}.dat
```

目录名**就是对方 wxid 的 md5**（已验：`89ad7cb37164df01448412d7b63829b1`
= md5("<WXID_FRIEND_A>")，`9e20f478899dc29eb19741386f9343c8`
= md5("filehelper")）。

V2 文件布局：

```
[0x00:0x06]  6B   签名  07 08 56 32 08 07      ← "V2"
[0x06:0x0A]  4B   aes_size   (LE)
[0x0A:0x0E]  4B   xor_size   (LE)
[0x0E:0x0F]  1B   padding 占位
[0x0F: …]         AES-128-ECB 段，长度 = ceil16(aes_size)   ← **不做 PKCS7 unpad**
[… : -xor_size]   16 字节占位（丢弃，不是图片数据）
[-xor_size : ]    单字节 XOR 段
```

**验证方式**（这一步非常值得记）：让绯栀给自己发一张已知的图
（`images/gen_9f816f698803f168.jpg`，578568 字节），取生成的
`9e93939518f3d1932c4351236304064b_h.dat`（578599 字节）：

* `aes_size=1024`、`xor_size=577544`、中间占位 16 字节
* XOR 段用 `0xF2` 解开后 == **原图尾部 577544 字节，逐字节相同**
* 1024 + 577544 = 578568 = 原图长度 ✅
* 完整解码结果与原图 **`plain == src` 为 True**（578568 字节全等）

所以结构、XOR key、偏移全部正确。缺的只有 AES 段那 1008 字节（图片头部）。

### 踩过的坑

1. **不要以为 4.x 还是单字节 XOR 全文件加密**。整文件 XOR `0x45` 会让开头
   变成 `42 4D`（"BM"），看着像 BMP —— 纯属巧合，因为 V2 头的
   `07 08` ^ `45` = `42 4D`。据此判断会一路错到底。
2. **XOR key 从尾部推**：尾两字节解密后应是 `FF D9`（JPEG EOI）。
   `_h` / `_t` 都是 `0xF2`；无后缀那档尾部不是 JPEG（中图重新编码过），推不出来，不影响。
3. `_t`（缩略图）是**独立重新编码**的，不是原图裁剪 —— 所以它的 XOR 段
   当然不等于原图尾部，这一点不要当成解密失败。
4. **绝对不能对 AES 段做 PKCS7 unpad**。社区脚本里有 `Padding.unpad(...)`，
   在本机会抛 `ValueError: Padding is incorrect`，然后整张图被当成解密失败丢掉。
   AES 段解出来**整段 1024 字节都是图片明文**，中间那 16 字节占位要丢弃、
   但 AES 段本身一字节都不能裁。这个坑害我第一版 `decrypt_dat` 返回 0/30。
5. 三档里 **`<id>.dat` 可能是微信自定义的 `wxgf`（HEVC 封装）**，视觉模型不认识；
   `_h` / `_t` 才是 jpg。所以定位到某一组之后，要在组内挑**最大的 jpg**，
   而不是按「文件最大」或「时间最新」挑。

---

## 四、图片 AES key：从磁盘派生（不用碰进程）

算法（社区实现 + 本机 4.1.9.23 复验）：

```
xor_key = uin & 0xFF
aes_key = MD5(f"{uin}{wxid}").hexdigest()[:16]      ← 16 字符 hex，按 ASCII 取 16 字节
```

`uin` 是微信内部用户号（十进制）。关键结构性约束：

> **账号目录名末 4 位 hex == md5(str(uin))[:4]**

本机目录 `<WXID_SELF>_dfb4` → 末 4 位 `dfb4`，而
`md5("3815394034")[:4] == "dfb4"`。又因为 xor_key 能从 `.dat` 末尾反推
（JPEG EOI = FF D9，实测 29 票一致为 `0xF2`），uin 的低字节被固定，
搜索空间压到 2^24：

```
for i in range(2**24):
    uin = (i << 8) | 0xF2
    if md5(str(uin)).digest()[:2] != bytes.fromhex("dfb4"): continue
    aes_key = md5(f"{uin}<WXID_SELF>").hexdigest()[:16]
    # 用魔数 + 完整解密验证
```

实测 17.9 秒枚举完，md5 前缀命中 **237 个**候选，再用 16 字节魔数筛只剩
**1 个**：`uin=3815394034 → aes_key=985dddf7c94992a0`。
与"扫进程内存"得到的结果完全一致（两条独立路径互证）。

本机结果已缓存到 `state/image_key.json`，换号/微信重装后会自动重新派生。

### 为什么要用派生而不是扫内存

一开始按社区 C 版思路扫微信进程，扫遍 5 个进程全部形态都没命中：

| 形态 | 候选数 | 结果 |
|---|---|---|
| ASCII 16 / 32 位 | ~120 万 | ✗ |
| 32 位 hex → fromhex | ~1.4 万 | ✗ |
| UTF-16LE 编码（Windows 微信大量用） | ~13 万 | ✗ |
| 磁盘 config/db_storage 里的候选 | 1304 | ✗ |

**根因不是格式，是时机**：key 只在微信渲染图片时才载入内存，
而本机微信 10-24 19:41 启动后没显示过"收到的"图片（发图走原图路径，不读 dat）。
派生法彻底绕开这个时序，且不要求微信在运行。

---

## 五、现存的 key 相关脚本

| 脚本 | 用途 |
|---|---|
| `find_key_by_derive.py` | 派生法（带已知明文对验证，调试用） |
| `find_img_key{,2,3}.py` | 三种形态的内存扫描器（现为兜底路径） |
| `activate_img_key.py` | 等"微信显示图片"再抓内存 key（派生失败时才需要） |
| `state/image_key.json` | 运行时产物，含 `uin` / `aes_key` / `xor_key` |

正常情况什么都不用做：`img_dat.extract_aes_key()` 自己走
「缓存 → 派生 → 扫内存」三级。

---

## 六、视觉端点：DeepSeek 自己就能看图（原先的判断是错的）

**更正**：一开始我按"deepseek-chat 是纯文本模型"来设计，把视觉绕到 claude 去了。
实际上 DeepSeek 已经上线**图像理解**（`deepseek-flash`），文档
`api-docs.deepseek.com/zh-cn/guides/vision`。同一个 key 通吃，不必跨供应商。

实测对比（同一张 240×240 街拍）：

| 后端 | 结果 | 耗时 |
|---|---|---|
| **`deepseek-flash`** | ✅ 准确，能认出"黄瓷砖墙""线路图""标牌上的 E" | **1.7~2 秒** |
| `claude-sonnet-4-6` | ✅ 也准确，细节略少 | 3~5 秒 |
| `synapse-grok` | ✗ 401 Invalid token | — |
| `synapse-gpt4o` | ✗ 503 No available channel | — |
| `synapse-gemini` | ✗ 403 无权访问 | — |
| `openrouter` | ✗ 401 | — |

所以 `vision.py` 改成 **deepseek-flash 主 + claude 兜底**。图片按 token 计费，
`detail=low` 缩到 512×512，单图上限 1024 token ≈ 0.0005 元/张。

### 两个坑

1. **`deepseek-flash` 是推理模型**，`max_tokens` 是「思考 + 正文」总预算。
   给 400 时 400 全烧在 `reasoning_tokens` 上，正文返回空串、
   `finish_reason=length` —— 看起来完全像"模型看不见图"。
2. 正解是 `"thinking": {"type": "disabled"}`：**5.9 秒 → 1.7 秒**，质量不降。
   （`reasoning_effort` 无效；`thinking.type` 只认 `disabled` / `auto`，
   传 `none` 会 422。）
3. 图片**只能放在 `user` 消息里**，system/assistant 带图直接 400。

---

## 七、联网搜索：改用 DeepSeek 官方 Search API

**最大的更正**：一开始以为"DeepSeek API 不带联网"，于是去爬 Bing / DuckDuckGo 的
HTML —— 那是次优方案。实际上 DeepSeek 已上线 **Search / Fetch API**
（自研搜索引擎），文档 `api-docs.deepseek.com/zh-cn/guides/search/`：

```
POST https://api.deepseek.com/v1/tools/search   5 元 / 1000 次成功请求
POST https://api.deepseek.com/v1/tools/fetch    5 元 / 1000 次成功请求
```

它比爬 HTML 好在：

* 返回结构化的 **`summary`**（600~800 字，官方注明"适用于给模型阅读"），
  不用自己拼摘要；
* **`date`**：发布时间，时效类问题（"最新/今天/几号"）全靠它；
* **`authority`**（0~4，≥3 极权威）、**`rerank_score`**（0~3，≥1.5 优质）：
  可以直接按质量过滤噪声；
* 支持 `site:` / `-site:` / `"精确短语"` / `lang:zh` / `after:2025-01-01`
  等搜索语法；
* 不受反爬影响，QPS 100。

实测"杭州明天天气"直接返回"明天多云，17℃～24℃"；
"流浪地球3什么时候上映"返回 `authority=4 / score=2.2` 的新闻，
summary 里就是"上部定档 2027 大年初一，下部 2027 暑期或 2028 春节"。

### 实现要点

* 源顺序：**Search API → Bing HTML → DuckDuckGo Lite**（后两个只在无 key、
  余额不足 402、限速 429 时兜底）。
* `need_content=False`（只取 summary，省带宽）；真要正文时用 `fetch_page()`
  走 Fetch API，拿 Markdown。
* 新增 `build_query()`：把口语压成检索词，不进 LLM（省一次调用）——
  「你说那个流浪地球3到底什么时候上映啊」→「流浪地球3什么时候上映」。
* 5 分钟结果缓存；`needs_search()` 的信号词表**从 autoreply.py 移到 search.py**
  （原来两处会漂移），autoreply 里改成 `needs_search = search.needs_search`。

### 原来爬虫方案的毛病（留作记录）

* **DuckDuckGo Lite 在国内网络下整体超时**（20 秒无响应），
  会把一条回复拖到拟人延迟之外 —— 现已降为末位备源、6 秒耐心。
* Bing 的"4 小时之前 / 2026年9月23日"时间戳原来被丢掉，恰恰是最该留的。

`persona.SEARCH_STYLE` 原文已经写得很好（不暴露"搜索"痕迹、查不到就说不知道），未改动。

---

## 八、接线方式（autoreply.py）

1. `should_reply()`：放行 `type=3`（原来只放行 `type=34` 语音）。
2. `handle()`：`type=3` → `_describe_image()`，**入库的是识别后的描述**，
   不是 `<img …/>` 标签（跟语音转文字同一个道理，否则模型看到的是尖括号）。
3. `_handle_batch()`：连发多条时，前面的图片也走同一条识别路径，
   带 `BATCH_IMAGE_LIMIT=3` 预算，超出记占位。
4. 失败一律退成 `[他发来一张图片，我这边没打开]`，让她说"再发一次"，**绝不卡死**。

`persona.VISION_STYLE`（新增 494 字）：告诉她那段描述就是她亲眼所见，
不许说"图片里/图中/这张图片显示"，只挑一个细节说；截图类要接住数字和时间；
没打开就直说。style_block 总长 7358 字，可控。

---

## 九、文件清单

| 文件 | 作用 |
|---|---|
| `vision.py` | 图片 → 中文描述（claude），带 md5 缓存 |
| `img_dat.py` | V2 dat 解密 + 消息↔文件匹配 + key 提取（含自动探测账号目录） |
| `search.py` | 重写加固（Bing 主源、时效字段、缓存、信号词表） |
| `activate_img_key.py` | 一次性激活图片 AES key |
| `find_img_key{,2,3}.py` | key 三种形态扫描器（ASCII / hex / UTF-16） |
| `probe_img_cache.py`、`probe_img_dat.py` | 当时的探测脚本（结论已并入 img_dat） |
| `vision_probe.py` | 视觉端点选型 |
| `_test_vision.py` | 四步冒烟自检 |
| `trigger_img_key.py` | 发一张图给 filehelper 用于造测试数据 |

`state/image_key.json`、`state/vision_cache.json` 是运行时产物。

---

## 十、下一步可做

1. **启动服务**即可生效（`pythonw run.py both`），当前各项均已自测通过。
2. 图片描述进**长期记忆**（他跟她说"这张是我妈"这类信息值得记住）——
   目前只进上下文，没进 `memory.py`。
3. 定位精度：现在主要靠「时间窗 + 同组挑最大 jpg」，连发多图时偶尔可能配错。
   更稳的做法是把 `cdnthumbwidth/height` 与实际缩略图尺寸做精确比对
   （XML 标注的档位和 `_t.dat` 实测尺寸不一致，只能靠宽高比兜），
   或者干脆解析 dat 文件名与 XML 里 fileid 的关系。
4. **表情包（type=47/sticker）仍不识别** —— 那是另一套格式，
   要做的话得先搞清楚收藏表情的本地缓存。
5. 缓存里没有的历史图片取不到（那几个会话的 `attach` 目录本就不存在）——
   这是微信自己的下载策略，不是解密问题。
