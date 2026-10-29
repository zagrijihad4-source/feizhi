# -*- coding: utf-8 -*-
"""只读探查 v1.3 账本结构（在副本上操作，不动原件）。"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\feizhi_pc\eval\source_verification_20261026"
           r"\work\source-verification-v1_1\verified_candidates_v1_3.sqlite3")
MOD = SRC.parent
sys.path.insert(0, str(MOD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

tmp = Path(tempfile.mkdtemp(prefix="ledger_probe_"))
dst = tmp / "l.sqlite3"
shutil.copy2(SRC, dst)
con = sqlite3.connect(str(dst))
con.row_factory = sqlite3.Row

print("表：", [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")])
print()
print("route × review_state：")
for r in con.execute("SELECT route, review_state, COUNT(*) n FROM candidates"
                     " GROUP BY route, review_state ORDER BY route, review_state"):
    print("   %-16s %-14s %d" % (r["route"], r["review_state"], r["n"]))
print()
print("pending/rejected 候选：")
for r in con.execute("SELECT candidate_key, route, review_state FROM candidates"
                     " WHERE review_state IN ('pending','rejected')"):
    print("   %-10s %-10s %s" % (r["candidate_key"], r["route"], r["review_state"]))
print()
for t in ("batch_receipts", "batches", "batch"):
    try:
        rows = con.execute("SELECT * FROM %s" % t).fetchall()
        print("表 %s：%d 行，列=%s" % (t, len(rows), rows[0].keys() if rows else "?"))
        for r in rows[:8]:
            d = dict(r)
            d.pop("payload", None)
            print("   ", json.dumps(d, ensure_ascii=False)[:180])
    except Exception as e:  # noqa: BLE001
        print("表 %s：%s" % (t, e))
con.close()

print()
print("=== 用 ReviewLedger 读一个 eligible 候选的结构 ===")
try:
    import review_ledger as RL
    led = RL.ReviewLedger(dst)
    pend = led.pending_reviews()
    print("pending_reviews()：", len(pend), "条")
    if pend:
        d = dict(pend[0])
        print("   键：", list(d.keys()))
    el = led.export_eligible()
    print("export_eligible()（无 batch_key）：", len(el), "条")
    if el:
        print("   首条：", json.dumps(el[0], ensure_ascii=False)[:400])
    led.close()
except Exception as e:  # noqa: BLE001
    print("ReviewLedger 调用失败：", type(e).__name__, e)

shutil.rmtree(tmp, ignore_errors=True)
