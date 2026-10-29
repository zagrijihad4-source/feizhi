# 绯栀发朋友圈 —— 技术档案（2026-10-15 夜 ~ 2026-10-16 凌晨）

## 一句话结论

**可行，且已做成可无人值守的实现**：切页 → 长按摄像机 → 写入中文 → 点发表/取消，
全流程实测通过。代码 `<PROJECT_ROOT>\feizhi_pc\moments.py` + `post_moment.py`。
唯一没做的是「真的按一下发表」——那需要决定发什么内容，留给 YG。

## 一、实测证据链

| 时间 | 动作 | 结果 |
| --- | --- | --- |
| 23:45:32 | DPI 感知 + 窗口识别修正 | 主窗 `hwnd=198768` 物理 rect `(1035,502,1349,972)`，摄像机点 `(2315,586)` |
| 23:46:04 | 激活 + 真实长按摄像机 1300ms | **弹出新窗口** `hwnd=267300`「朋友圈」= 纯文字发表框 |
| 23:47:23 | 剪贴板 + Ctrl+V 写入 | 文字进框，**「发表」按钮由灰变绿** |
| 23:48:13 | 跨缩放比复算 | dpi=120 布局下公式 `(1172,89)` vs 截图 `(1171,90)`，**误差 1px** |
| 23:52:42 | 三轮稳定性测试（长按→写入→取消） | 3/3 成功，每轮 ~17s，每轮 hwnd 都不同（确认是新窗口） |
| 23:54:17 | 同上 + 对照组 | 空框 `enabled=False`(灰) → 写入后 `True`(绿)，判据区分度确认 |
| 23:55:10 | LLM 现写一条并填入 | 70 字文案完整入框，`button_enabled=True`，自动清理 |
| 00:02:39 | 点击方式对照实验 | 真实鼠标 220ms ✓、PostMessage 到 Chrome 宿主 ✓ 都能切页 |
| 00:03:06 | 点左侧栏切回朋友圈页 | 成功，绿高亮回到「朋友圈」 |
| 00:04:00 | **自愈测试**：聊天页 → 自动切回朋友圈 → 长按 | 一次通过，发表框弹出 |

截图证据：`tmp\` 下 `probe_hwnd_198768.png`、`moments_press_real.png`、`moments_typed.png`、
`crop_cam_check.png`、`moments_test\round_*.png`、`clicktest\*.png`；
`feizhi_pc\logs\moments_*_before.png`、`selfheal_*.png`。

## 二、关键技术发现（都会咬人）

### 1. 微信 4.x = Qt 外壳 + Chromium 渲染
主窗 `Qt51514QWindowIcon` 的子窗口：

```
hwnd=32903448  Chrome_WidgetWin_0              title=微信          rect=(507,59,725,756)
hwnd=13635910  Chrome_RenderWidgetHostHWND     title=Chrome Legacy rect=(507,59,725,757)  ex=0x20 TRANSPARENT
hwnd=10620988  Intermediate D3D Window                              ex=0x00280024 TRANSPARENT LAYERED
```

内容区是 **CEF（Chromium）**画的，而且带 `WS_EX_TRANSPARENT`。
这解释了第三方项目记录的「UIA/坐标点击落到背后窗口」现象，也解释了
`WindowFromPoint` 在微信内容区返回桌面（命中了跳过透明层的桌面窗口）。

### 2. DPI 感知必须在**模块导入**时设置
`set_dpi_aware()` 只放在构造函数里不够：任何 `import moments` 后直接调
`find_main_window()` 的脚本都会拿到**虚拟化坐标**（窗口"看起来"缩小 1.25 倍 → 886
而不是 1108），于是点击全部打偏。实测踩过一次，排查了两轮。
现已改为模块顶部导入时执行（`_DPI_MODE = set_dpi_aware()`）。

### 3. `GetPixel` 逐点扫像素会超时
扫 5.7 万点用了 >180 秒没跑完（屏幕 DC 的 GetPixel 每次约 2~3ms）。
改用一次 `BitBlt` + `GetDIBits` 抓整块区域到内存，再纯字节访问 —— 同样扫描 3 秒内完成。
实现：`moments.Grab`。`green_ratio` 也换成它。

### 4. 窗口识别不能只看标题
`FindWindowW(None,"微信")` 曾返回 `(-21333,-21333,158,26)` 的屏幕外幽灵窗；
同一进程还有 `12915540`（906x836，`visible=False`，`PrintWindow` 全黑）。
判据：**可见 + 面积最大 + 类名前缀 `Qt5`**。

### 5. 发表框相关
- 点「取消」会弹**模态浮层「将此次编辑保留？」[保留][不保留]**，它盖住输入框，
  会把后续 Ctrl+V 全吃掉 —— 只点一次「取消」关不掉窗口（踩过，导致三轮测试全部假阳性）
- EP「发表」按钮的**正中心是白色「发表」二字**，单点取色会把绿色按钮判成灰的；
  必须扫一片区域算绿色占比（阈值 0.35）
- 输入框为空时按钮灰、有内容时绿 —— 这是唯一低成本的"文字真的进去了"信号

### 6. 左侧栏导航
- 图标位置随窗口移动/DPI 变化，必须用**相对主窗左上角的 DIP 偏移**
  （实测 dpi=120、窗口 (122,19) 时「朋友圈」图标在屏幕 (168,334)，换算 36.8 / 252.0 DIP）
- 点击需要**按住约 220ms**；60ms 的短点击在对照实验里没切成功
- 切页是**幂等**的（已在朋友圈页时点击无副作用），所以可以每次发帖前无脑先切一次
- 摄像机只在朋友圈页存在；在聊天页长按摄像机位置会误触 `⊕`/搜索（就在旁边），
  所以流程必须是**先切页再长按**，不能反过来

### 7. 中文输入
Qt/CEF 都不吃 `WM_SETTEXT`，正解是**剪贴板 + 真实 Ctrl+V**（两边项目独立得出同一结论）。
写剪贴板前先备份、事后恢复，不污染用户剪贴板。

## 三、代码与用法

`<PROJECT_ROOT>\feizhi_pc\moments.py`（纯 ctypes，无第三方依赖）：

```python
from moments import MomentsPublisher
MomentsPublisher().post("文案", dry_run=True)     # 填好但不发表
```

CLI：

```bash
python moments.py point       # 只读自检：主窗 / 摄像机坐标 / 发表框状态
python moments.py open        # 切页 + 长按摄像机 -> 发表框
python moments.py write --text "..."
python moments.py publish     # 点「发表」（先确认输入框有内容）
python moments.py cancel      # 关掉发表框（含「不保留」浮层）
python moments.py post --text "..." [--dry-run]
```

`<PROJECT_ROOT>\feizhi_pc\post_moment.py`（发一条，默认 dry-run）：

```bash
python post_moment.py --text "文案"            # 只填不发表
python post_moment.py --generate               # 让模型按人格现写一条，填入但不发表
python post_moment.py --generate --send        # 生成并直接发
```

标定参数落盘 `feizhi_pc\state\moments_calib.json`；已发内容留档 `state\moments_posted.json`。

| 参数 | 值 | 含义 |
| --- | --- | --- |
| `camera_from_right_dip` / `camera_from_top_dip` | 46 / 56 | 摄像机图标，相对主窗右上角 |
| `moments_tab_dip` | 36.8 / 252.0 | 左侧栏「朋友圈」，相对主窗左上角 |
| `publish_btn_ratio` / `cancel_btn_ratio` | 0.347,0.837 / 0.663,0.837 | 发表框内按钮 |
| `keep_draft_btn_ratio` / `discard_btn_ratio` | 0.341,0.558 / 0.661,0.558 | 「保留编辑？」浮层按钮 |
| `hold_ms` | 1300 | 长按摄像机时长（重试时 +25%） |

## 四、网上现成方案调研（2026-10-15 夜）

| 项目 | 结论 |
| --- | --- |
| [wechatauto-replica](https://pypi.org/project/wechatauto-replica/1.2.4/) | **明确放弃发朋友圈**："4.x 的发表为自绘界面操作，不可靠自动化"，只保留读取/点赞/评论。但它记录的 `WS_EX_TRANSPARENT` 命中测试问题、剪贴板输入、风控经验都被本项目验证/复用 |
| [aixed/WeChat-Hook](https://github.com/aixed/WeChat-Hook) | 支持到 4.1.10.27，接口只有 SendTextMsg / SendImgMsg / ForwardXMLMsg / Decode_Pic / GetSelfProfile / QueryDB，**没有朋友圈写接口** |
| [wxhelper](https://gitee.ltd/wechat/wxhelper) | 只有 `getSNSFirstPage/getSNSNextPage`（读），无写 |
| 本地 `wx-basic-bridge` | README 明写不含朋友圈功能 |

**没有一个能直接复用的发送实现** —— 但也没有证据说"做不到"，只是别人没走通我们这条路。
差别在于：他们依赖 UIA 命中自绘控件；我们直接投递**真实鼠标事件**（SendInput），
Qt 主窗会把事件路由给 CEF 内容层，于是长按和点击都能生效。

## 五、风险与限制

1. **自绘/浏览器内核界面天生脆**：微信改版、CEF 版本变化都可能让坐标失效。
   已用 DIP 比例 + 幂等切页 + 失败重试缓解，但不是根治。坐标参数集中在 calib 文件里便于重标。
2. **风控**：wechatauto 作者本机触发过风控被要求重新登录。若接入自动发帖必须：
   低频（每天最多 1 条）、拟人节奏（已实现落点抖动/分两段移动/时长随机）、不要批量深夜操作。
3. **抢前台**：整个流程要激活微信窗口，会打断用户当前操作。
4. **发布不可逆**：发表后好友可见，删除要去手机端。
5. **只覆盖纯文字**：图片/视频朋友圈走发表框的「+」，本档案未涉及。

## 七、2026-10-16 上午：后台能力实测（停电后复测）

### 关键纠正：左侧栏那个圆图标是「发现」，不是「朋友圈」

只点它只会展开发现列表（朋友圈/视频号/搜一搜/游戏/小程序），**内容区仍然空白、根本没有摄像机图标**，
长按必然落空。必须**两步**：点「发现」→ 点列表第一项「朋友圈」。

这是昨晚"后台长按失败"的真正原因（当时微信停在发现页的「游戏」子页）。
判据很便宜：摄像机图标位置的白色像素占比，在朋友圈页是 **0.10**，不在是 **0.00**。

### 后台能力矩阵（全程不调用 activate、不移动真实光标）

| 环节 | 后台可做 | 手段 | 实测 |
| --- | --- | --- | --- |
| 切到朋友圈页 | ✅ | `PostMessage` 点击（发现 → 朋友圈） | 微信处于后台时成功，选中项 [208]→[424] |
| 长按摄像机 | ✅ | `PostMessage` 按下/保持/抬起 | 发表框弹出，**微信主窗全程没被抢到前台** |
| 写入文字 | ✅ | `WM_CHAR` 逐字符（含代理对处理） | 按钮由灰变绿，不碰剪贴板、不需要焦点 |
| 点发表 / 取消 | ❌ | 需真实鼠标 | 纯 `PostMessage` 连试两次都没反应 |

### 唯一躲不掉的打扰

**微信弹出发表框时会自己 `SetForegroundWindow`**（实测弹出后前台立刻变成发表框 hwnd），
这不是我们抢的，是微信的业务行为。所以"发朋友圈完全无感"做不到；
能做的只是：过程中不主动抢，结束后把前台还给用户原来的窗口
（`MomentsPublisher._restore_foreground()`，仅当当前前台属于微信进程时才归还，
不会抢走用户后来自己切过去的窗口）。

### 代码现状

`MomentsPublisher(background=True)` 为**默认**：切页/长按/写入全走 PostMessage + WM_CHAR；
`background=False` 时退回真实鼠标。`ensure_moments_page()` 自带页面自检，
已经在朋友圈页则不做多余点击。

跨会话复用的实测命令：

```bash
cd <PROJECT_ROOT>\feizhi_pc
python post_moment.py --text "文案"            # 后台填好，不发表
python post_moment.py --text "文案" --send     # 后台填好 + 真实鼠标点发表
```

### 关于「真正无感」的另一条路

彻底后台只有走 Hook：逆向 4.1.9.23 的发表内部函数（组装 SNS protobuf 直接发包），
而不是驱动界面。本地 `wx-basic-bridge` 目前不含朋友圈能力，
网络上的 wxhelper / aixed WeChat-Hook 到 4.1.x 也都只有读取接口。
工作量显著大于 UI 路线，但一旦做成就不再受界面改版与焦点问题影响。

## 九、自动发布（无人值守）与锁屏边界 —— 2026-10-16 下午

### 真实发布已验证

13:00 用 `post_moment.py --send` 真发了一条，截图确认朋友圈顶部出现该条（「绯栀 · 1分钟前」）。
至此「切页 → 长按 → 写入 → 点发表 → 前台归还」全链路闭合。

### 调度器

`feizhi_pc/moment_scheduler.py`（已作为独立进程常驻，PID 见 `logs/moment_scheduler.log`）：

| 策略项 | 默认 | 说明 |
| --- | --- | --- |
| `max_per_day` | 1 | 每天最多一条 |
| `window_start/end` | 09:00–23:00 | 只在白天 |
| `min_gap_hours` | 6 | 两条之间最少间隔 |
| `jitter_minutes` | 90 | 目标时刻随机浮动，不整点 |

- 每天的目标时刻随机生成，落在时段中间 60% 区间后再加抖动
- 文案由 LLM 按人格现写（复用 `post_moment.generate()`），并参考最近 8 条避免重复
- 状态落盘 `state/moment_schedule.json`（保留 60 天），发布历史 `state/moments_posted.json`
- 命令：`--status` / `--once` / `--once --dry-run` / `--force` / `--loop`

### 锁屏边界（本方案的天花板）

微信的「发表」按钮**只认真实输入事件**。以下四种"不碰真实输入"的尝试**全部失败**：

| 方案 | 结果 |
| --- | --- |
| `PostMessage` 鼠标 down/up | 无效（对主窗左侧栏有效，对这个弹窗无效） |
| `PostMessage` Enter | 无效（窗口与按钮状态都没变，多半只是换行） |
| `PostMessage` Ctrl+Enter | 无效 |
| `SetCursorPos` 移动光标 + `PostMessage` 点击 | 无效 |

结论：**锁屏时无法发表**（锁屏后 SendInput 被 Winlogon 接管）。
而切页 / 长按 / 写入这三步走 `PostMessage` + `WM_CHAR`，锁屏不受影响。

调度器因此内置锁屏检测（`OpenInputDesktop` 判断输入桌面是否 `Default`）：
**发现锁屏就把当天的发布顺延**，等解锁后的下一个检查周期再发，不会硬撞失败。

要突破这个天花板只有一条路：不走界面，直接 Hook 微信内部的发帖函数（组装 SNS 包发出）。
那是另一个量级的工程，需要从逆向 4.1.9.23 开始，但做成之后连锁屏和界面改版都不怕。



## 十、未完成 / 下一步

- [x] ~~真发一条~~ —— 2026-10-16 13:00 已发并截图确认
- [x] ~~无人值守调度~~ —— `moment_scheduler.py` 已常驻（见第九节）
- [ ] 发布后确认：目前只确认"窗口关闭 + 截图"，可加"回读朋友圈顶部"的二次校验
- [ ] 持久化：调度器是独立进程，电脑重启后要重新拉起（是否接进 `run.py` / 守护脚本待定）
- [ ] 锁屏场景：要锁屏也能发，只能走 Hook（见第九节）
- [ ] 可选：图片/视频朋友圈（发表框的「+」入口）
- [ ] 可选进阶：热激活 Qt accessibility gate → 走 UIA
