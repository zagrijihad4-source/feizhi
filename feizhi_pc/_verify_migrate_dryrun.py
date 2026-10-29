# -*- coding: utf-8 -*-
"""生产副本 dry-run：迁移 → 落库 → 重载 → 召回渲染，全程**不碰生产**。

YG 的门槛是「在副本完成落库、重载、召回验证后，才迁移生产」。
这个脚本就是那道门槛的检查单：只读生产文件，所有写操作都落在临时副本上。

用法: python _verify_migrate_dryrun.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
PROD = HERE / "state" / "feizhi_memory.json"
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
import memrec as R      # noqa: E402
import memory as M      # noqa: E402

OK, NG = "[ OK ]", "[FAIL]"
_RES = {"pass": 0, "fail": 0}


def check(label, cond, detail=""):
    _RES["pass" if cond else "fail"] += 1
    print("   %s %-48s %s" % (OK if cond else NG, label, str(detail)[:52]))
    return cond


def head(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def ms(y, mo, d, h=21):
    return int(datetime(y, mo, d, h, tzinfo=R.BEIJING).timestamp() * 1000)


def main() -> int:
    if not PROD.exists():
        print("找不到生产文件：", PROD)
        return 2
    prod_sha, prod_mtime = sha(PROD), PROD.stat().st_mtime
    raw = json.loads(PROD.read_text(encoding="utf-8"))
    print("生产文件：", PROD)
    print("   sha256[:16] =", prod_sha)
    print("   facts=%d events=%d last_id=%d last_mid=%s"
          % (len(raw.get("facts", [])), len(raw.get("events", [])),
             raw.get("last_id", 0), raw.get("last_mid", "（无此字段）")))

    tmp = Path(tempfile.mkdtemp(prefix="feizhi_dryrun_"))
    ok = True
    try:
        copy = tmp / "feizhi_memory.json"
        shutil.copy2(PROD, copy)

        head("0. 未迁移状态下的召回（生产当前就是这个状态，最容易悄悄坏）")
        m0 = M.FeizhiMemory(copy)
        v0 = m0._view()
        n_f0 = sum(1 for x in v0 if x.get("kind") == "fact")
        n_e0 = sum(1 for x in v0 if x.get("kind") == "event")
        ok &= check("未迁移时 kind 也能正确归类",
                    n_f0 == len(raw.get("facts", []))
                    and n_e0 == len(raw.get("events", [])),
                    "%d fact / %d event" % (n_f0, n_e0))
        r0 = m0.render()
        ok &= check("render 抽出事实段", "关于<OWNER>：" in r0)
        ok &= check("render 抽出事件段", "最近这些天：" in r0)
        live0 = R.recallable(v0)
        # ★ 不能断言「可召回 = 全部」：生产 events 已超上限（49 > 40），
        #   最旧的 9 条会被容量自动归档，本来就不该召回。
        ok &= check("可召回条数 = 未归档记录数",
                    len(live0) == sum(1 for x in v0 if not x.get("archived")),
                    "%d 可召回 / 全部 %d" % (len(live0), len(v0)))

        head("1. 迁移（副本）")
        m = M.FeizhiMemory(copy)
        wm_before = int(m.data.get("last_id", 0))
        # ★ 生产记忆已不是纯旧格式：新增记录本身带 id / 来源 / 时间。
        #   所以"迁移是否补造来源"只能看**这次新分配 id** 的那部分。
        pre_ids = {x.get("id") for x in m._view() if x.get("id")}
        info = m.migrate()
        view = m._view()
        fresh = [x for x in view if x.get("id") not in pre_ids]
        ok &= check("记录全部拿到 id", all(x.get("id") for x in view),
                    "touched=%d" % info["touched"])
        ok &= check("id 唯一", len({x["id"] for x in view}) == len(view),
                    len(view))
        ok &= check("消息水位不变", int(m.data.get("last_id", 0)) == wm_before,
                    "%d → %d" % (wm_before, m.data.get("last_id")))
        ok &= check("记忆编号独立推进", int(info["last_mid"]) >= len(view),
                    info["last_mid"])
        ok &= check("迁移新增的记录未补造来源",
                    all(x["source_msg_ids"] == [] for x in fresh),
                    "%d 条" % len(fresh))
        ok &= check("迁移新增的记录未把入库日当事件时间",
                    all(x["event_time"] is None for x in fresh))

        head("2. 落库（在副本上新增 + 更新）")
        src = [{"id": 7001, "role": "user", "text": "明天那个考试我有点慌",
                "sent_at_ms": ms(2026, 10, 20)}]
        added = m.add_record({"kind": "event", "text": "<OWNER>明天要考试",
                              "time_raw": "明天", "time_anchor_msg_id": 7001,
                              "source_msg_ids": [7001]}, src)
        ok &= check("新增走完整校验", added["record"]["event_time"] == "2026-10-21",
                    added["record"]["event_time"])
        ok &= check("新增推进记忆编号、不动水位",
                    int(m.data["last_id"]) == wm_before
                    and info["last_mid"] + 1 == int(m.data["last_mid"]),
                    "mid=%s wm=%s" % (m.data["last_mid"], m.data["last_id"]))
        up = m.update_record(added["record"]["id"], {"certainty": "mid"})
        ok &= check("普通 patch 保住核验",
                    up["record"]["event_time"] == "2026-10-21"
                    and up["record"]["time_basis"] == R.TB_MESSAGE,
                    up["record"]["event_time"])
        try:
            m.add_record({"kind": "event", "text": "<OWNER>要交材料",
                          "time_basis": "manual", "event_time": "2026-11-05",
                          "source_msg_ids": [7001]}, src)
            ok &= check("抽取入口拒绝自报 manual", False)
        except R.RecordError:
            ok &= check("抽取入口拒绝自报 manual", True)

        head("3. 重载")
        m2 = M.FeizhiMemory(copy)
        ok &= check("条数一致", len(m2._view()) == len(m._view()),
                    "%d/%d" % (len(m2._view()), len(m._view())))
        ids2 = [x["id"] for x in m2._view()]
        ok &= check("id 全部保留", ids2 == [x["id"] for x in m._view()])
        kept = [x for x in m2._view() if x["id"] == added["record"]["id"]]
        ok &= check("新增记录重载后仍在", bool(kept))
        ok &= check("时间结论重载后仍在",
                    kept and kept[0]["event_time"] == "2026-10-21",
                    kept[0]["event_time"] if kept else "")
        ok &= check("记忆编号重载后一致",
                    int(m2.data["last_mid"]) == int(m.data["last_mid"]),
                    m2.data["last_mid"])

        head("4. 召回渲染")
        text = m2.render()
        ok &= check("渲染非空", bool(text), "长度=%d" % len(text))
        ok &= check("新增记忆进入 prompt", "考试" in text)
        ok &= check("渲染不含归档记录",
                    not any(x["text"] in text for x in m2._view()
                            if x.get("archived")))
        ok &= check("渲染不含内部字段名",
                    "source_msg_ids" not in text and "time_basis" not in text)
        existing = m2.render_existing()
        ok &= check("抽取用的已有记忆非空", bool(existing))
        ok &= check("已有记忆带入库日", "入库日=" in existing
                    or "（还什么都没记）" in existing)

        head("5. 生产文件未被改动")
        ok &= check("sha256 未变", sha(PROD) == prod_sha,
                    "%s / %s" % (prod_sha, sha(PROD)))
        ok &= check("mtime 未变", PROD.stat().st_mtime == prod_mtime)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    head("结论：%d 通过 / %d 失败" % (_RES["pass"], _RES["fail"]))
    if ok and _RES["fail"] == 0:
        print("副本验证通过；生产迁移仍需人工下令后单独执行。")
    return 0 if ok and _RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
