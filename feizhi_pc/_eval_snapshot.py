# -*- coding: utf-8 -*-
"""第 0 步基础设施：冻结一致快照 + dump 记忆全量 + 固定实验配置。

冻结内容：
  snapshot/<ts>/context.sqlite3          ← 用 sqlite3 backup API（正确处理 WAL/未提交写）
  snapshot/<ts>/feizhi_memory.json
  snapshot/<ts>/feizhi_life.json
  snapshot/<ts>/manifest.json            ← 文件哈希 + 代码哈希 + 时间，用于固定实验配置

为什么用 backup API 而不是复制文件：直接 copy 主库可能漏掉 WAL 里未 checkpoint 的
页，也会和正在写的进程产生撕裂读。backup() 走 SQLite 自己的一致性快照机制。

用法:
    python _eval_snapshot.py
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

STATE = Path(r"<PROJECT_ROOT>\feizhi_pc\state")
CODE_DIR = Path(r"<PROJECT_ROOT>\feizhi_pc")
DB = STATE / "context.sqlite3"
SNAP_ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc\eval\snapshots")

CODE_FILES = ["memory.py", "store.py", "persona.py", "autoreply.py", "history.py"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = SNAP_ROOT / stamp
    out.mkdir(parents=True, exist_ok=True)

    # 1) SQLite 一致性快照
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(out / "context.sqlite3"))
    with dst:
        src.backup(dst)
    n_msg = src.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    n_out = src.execute("SELECT COUNT(*) FROM outbound").fetchone()[0]
    src.close()
    dst.close()

    # 2) 记忆 / 生活状态
    for name in ("feizhi_memory.json", "feizhi_life.json"):
        p = STATE / name
        if p.is_file():
            (out / name).write_bytes(p.read_bytes())

    # 3) manifest：固定实验配置
    manifest = {
        "snapshot": stamp,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db": {"messages": n_msg, "outbound": n_out,
               "sha256_16": sha(out / "context.sqlite3")},
        "files": {p.name: {"sha256_16": sha(p), "bytes": p.stat().st_size}
                  for p in out.iterdir() if p.is_file()},
        "code": {f: sha(CODE_DIR / f) for f in CODE_FILES if (CODE_DIR / f).is_file()},
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("快照目录:", out)
    print("messages: %d 条, outbound: %d 条" % (n_msg, n_out))
    print("代码哈希:")
    for k, v in manifest["code"].items():
        print("   %-14s %s" % (k, v))
    print("manifest ->", out / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
