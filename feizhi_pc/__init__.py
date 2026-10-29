"""feizhi_pc —— 把 Feizhi 的自动回复/主动消息逻辑接到 PC hook 桥上。

模块：
  bridge.py     与 hook 桥交互（读 inbox、发 outbox）
  store.py      SQLite 对话上下文
  autoreply.py  自动回复（复用 Feizhi 的 HermesReplyGenerator）
  proactive.py  主动发消息
  run.py        统一入口

与原 Feizhi 的差异：底层不再是 ADB 操作手机微信，而是 PC 端 hook 注入。
上层人格与生成逻辑完全沿用，避免重写。
"""

__all__ = ["bridge", "store", "autoreply", "proactive"]
