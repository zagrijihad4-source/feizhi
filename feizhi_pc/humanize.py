"""人类化时序 —— 让「多久回、打多久、隔多久再发」像真人。

为什么不直接改 prompt
--------------------
人格（说什么）由 `persona.py` 的提示词管；**节奏**（什么时候发）是纯工程问题。
放在这里可以独立调参、独立测试、单独开关，也不会把 prompt 撑长抬高 token 成本。

关键约束：所有延迟都**不得阻塞收消息的主循环**
--------------------------------------------
早期实现里 `_send_plan` 直接 `time.sleep`，一旦把延迟拉长（真人有时几分钟才回），
这段时间内主循环就收不到新消息——表现为「聊到一半卡住，之后一次性冒出一堆回复」。
所以本模块只**计算**延迟，实际 sleep 一律由调用方的后台发送线程执行。

关闭方式：环境变量 `FEIZHI_HUMANIZE=0`（回到原来的固定短延迟，便于对照测试）。
"""
from __future__ import annotations

import os
import random
from datetime import datetime

ENABLED = os.environ.get("FEIZHI_HUMANIZE", "1").lower() not in ("0", "false", "no")


def _activity_factor(now: datetime) -> float:
    """一天中的活跃度系数：越大，响应越慢。

    注意别调太狠：这里会与下面的三段抽样相乘，深夜若给 5.0，
    最慢那一档（45~180s）会放大到 15 分钟，实际体验像「不回消息」。
    """
    h = now.hour
    if 1 <= h < 7:      # 深夜，多半在睡
        return 2.5
    if 7 <= h < 9:      # 刚醒，还没拿起手机
        return 1.5
    if 9 <= h < 23:     # 白天正常
        return 1.0
    return 1.6          # 23:00~01:00，准备睡了


def reaction_delay_ms(text_len: int = 0, now: datetime | None = None) -> int:
    """「看到消息 → 开始回」的延迟。

    按三段抽样模拟真人状态：
      60% 正在看手机      1.5 ~ 8 秒
      30% 在忙别的        8 ~ 45 秒
      10% 离开了          30 ~ 90 秒
    再乘上当前时段系数；对方消息越长，越可能多看一眼再回。

    ★ 上限 25 秒（原来 180 秒）。180 秒那一档和「像没回」没有区别：
      实测 2026-10-18 23:54:59 生成的那条回复，因为正文里混进了网关的
      <ds_safety> 标签（105 字），reaction 放大到 120 秒 + typing 20 秒，
      整整憋了 160 秒才送达。真人不会为一句家常话等这么久。
      字数放大也收敛为「每 200 字 +1 成」，长文本不再指数级拖慢时序。
    """
    if not ENABLED:
        return random.randint(800, 2000)
    now = now or datetime.now()
    r = random.random()
    if r < 0.60:
        base = random.uniform(1500, 8000)
    elif r < 0.90:
        base = random.uniform(8000, 30000)
    else:
        base = random.uniform(25000, 50000)
    base *= _activity_factor(now)
    base *= 1.0 + min(max(text_len, 0), 300) / 2000.0
    return int(min(base, 25000))


def typing_delay_ms(text: str) -> int:
    """输入这段文字要多久。

    中文手机打字节律约 3~6 字/秒，再叠加一点「想一下 / 改一下」的时间。
    上限 9 秒（原来 20 秒）：一行字打到 20 秒，读起来已经不像人了，
    而且它会直接叠加在 reaction 延迟上，把一条普通回复拖成分钟级。
    """
    n = len(text or "")
    if not ENABLED:
        return min(300 + n * 60, 1500)
    if n == 0:
        return random.randint(300, 900)
    per_char = random.uniform(170, 330)          # ms / 字
    total = n * per_char + random.uniform(0, 1500)
    return int(min(total, 9000))


def gap_delay_ms() -> int:
    """连发两条之间的间隔（打完一条，停一下再打第二条）。"""
    if not ENABLED:
        return random.randint(400, 1200)
    return int(random.uniform(700, 3200))


def humanize_plan(plan, now: datetime | None = None):
    """⚠️ 已废弃，勿用。

    Feizhi 的 ReplyPlan.messages[i] 是**不可变 dataclass**，给它赋值会抛
    `cannot assign to field 'think_before_ms'`（2026-10-14 15:25 因此整整三小时
    一条回复都没发出去）。现在时序由 autoreply._send_plan 在发送时现算，不再改动 plan。
    保留本函数只是为了说明这段历史，实际不要调用。
    """
    return plan


def describe() -> str:
    """给自己看的配置摘要（日志/自检用）。"""
    if not ENABLED:
        return "humanize: OFF（固定短延迟）"
    now = datetime.now()
    return ("humanize: ON  时段系数=%.1f  示例反应延迟=%dms  打10字=%dms"
            % (_activity_factor(now), reaction_delay_ms(0, now),
               typing_delay_ms("一二三四五六七八九十")))
