"""只读解析微信收藏表情数据库。

微信 4.1.9.23 的收藏表情元数据在
  <WECHAT_DATA>\\<wxid>\\db_storage\\emoticon\\emoticon.db
（图片本体在 business\\emoticon\\Persist\\<hash2>\\<md5>，加密存储）

本脚本先把 db（含 -wal/-shm）复制到临时目录再打开，绝不动原文件。
目的是确认该库是否含 CDN URL / fileid —— 这决定「发送任意收藏表情」能否脱离重放。

用法:
    python read_emoticon_db.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

SRC = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\db_storage\emoticon\emoticon.db")
TMP = Path(r"<PROJECT_ROOT>\tmp")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"源库不存在: {SRC}")
        return 1
    TMP.mkdir(parents=True, exist_ok=True)
    dst = TMP / "emoticon.db"
    for ext in ("", "-wal", "-shm"):
        s = Path(str(SRC) + ext)
        if s.exists():
            shutil.copy2(s, Path(str(dst) + ext))
            print(f"复制 {s.name}  ({s.stat().st_size} 字节)")

    con = sqlite3.connect(str(dst))
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    cur = con.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"\n表: {tables}\n")

    for t in tables:
        print(f"{'='*70}\n## {t}")
        try:
            cols = cur.execute(f"PRAGMA table_info({t})").fetchall()
            print("  字段: " + ", ".join(f"{c[1]}:{c[2]}" for c in cols))
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  行数: {n}")
            if n:
                names = [c[1] for c in cols]
                for row in cur.execute(f"SELECT * FROM {t} LIMIT 6"):
                    vals = []
                    for k, v in zip(names, row):
                        if isinstance(v, bytes):
                            v = f"<blob {len(v)}B>"
                        s = str(v)
                        if len(s) > 90:
                            s = s[:90] + "…"
                        vals.append(f"{k}={s}")
                    print("   - " + "; ".join(vals))
        except Exception as e:
            print(f"  读取失败: {e}")
        print()
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
