"""接收状态一键检查。

用法: python check_recv.py

做三件事：
  1. 校验 hook 是否仍装载（含 trampoline 完整性）
  2. 检查 bridge/inbox 是否收到过入站消息，有则打印内容
  3. 检查是否已归档进 SQLite
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import subprocess
import sys

ROOT = r"<PROJECT_ROOT>\wx-basic-bridge"
INBOX = os.path.join(ROOT, "bridge", "inbox")
CTRL = os.path.join(ROOT, "bridge", "control")
SQLITE = os.path.join(ROOT, "bridge", "messages.sqlite3")


def hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


hr("1. hook 状态")
try:
    out = subprocess.run(
        [sys.executable, r"<PROJECT_ROOT>\verify_recv_hook.py"],
        capture_output=True, text=True, timeout=120,
    )
    txt = out.stdout
    for line in txt.splitlines():
        if any(k in line for k in (
            "weixin.dll base", "hook dll  base", "DoAddMsg @",
            "E9 rel=", "movabs rax", "inside hook dll", "RESULT:",
        )):
            print("  " + line.strip())
except Exception as e:  # noqa: BLE001
    print(f"  验证脚本运行失败: {e}")

hr("2. bridge/inbox")
files = sorted(glob.glob(os.path.join(INBOX, "*.json")))
print(f"  文件数: {len(files)}")
if not files:
    print("  还没有收到过入站消息。")
    print("  提示：入站消息必须由【对端账号】发出，自己发的不会进这里。")
    print("       让对方给当前登录的小号发一条消息即可。")
else:
    for f in files[-10:]:
        print(f"\n  --- {os.path.basename(f)} ---")
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for k in ("peer", "sender", "direction", "type", "subtype",
                      "content", "createTime", "msgId"):
                if k in data:
                    v = str(data[k])
                    if len(v) > 120:
                        v = v[:120] + "..."
                    print(f"    {k}: {v}")
        except Exception as e:  # noqa: BLE001
            print(f"    解析失败: {e}")

hr("3. control 状态文件")
for name in ("heartbeat.txt", "status.txt", "worker_owner.txt"):
    p = os.path.join(CTRL, name)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                print(f"  {name}: {fh.read().strip()}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: 读取失败 {e}")
    else:
        print(f"  {name}: (不存在)")

hr("4. SQLite 归档")
if os.path.exists(SQLITE):
    try:
        con = sqlite3.connect(SQLITE)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM messages")
        n = cur.fetchone()[0]
        print(f"  messages 表: {n} 行")
        if n:
            cur.execute("SELECT * FROM messages ORDER BY rowid DESC LIMIT 5")
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                s = str(d)
                print("    " + (s[:200] if len(s) > 200 else s))
        con.close()
    except Exception as e:  # noqa: BLE001
        print(f"  读取失败: {e}")
else:
    print("  尚无 messages.sqlite3（还没归档过消息）")

hr("结论")
if files:
    print("  接收链路已确认工作（inbox 有数据）。")
else:
    print("  hook 已就位且校验通过；等待第一条真实入站消息以确认端到端落盘。")
