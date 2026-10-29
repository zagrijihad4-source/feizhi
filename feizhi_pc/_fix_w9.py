import io
p = "_test_extract_wiring.py"
s = io.open(p, encoding="utf-8").read()

old = '''        ok &= check("已进入召回", "写小说" in m9.render())'''
assert s.count(old) == 1
new = '''        # ★ 2026-10-28 闸门接线后行为变了：补来源只把它移出隔离区，
        #   **不等于语义批准**（memrec.promote_quarantined 的矩阵明写
        #   「旧 pending / rejected → 保持阻断」）。以前这条能过，是因为
        #   抽取链路把 gate 硬编码成 legacy，绕过了矩阵 —— 那正是要修的缺陷。
        #   现在提升后仍 pending，需要闸门放行才召回。
        ok &= check("提升后仍是 pending（补来源≠批准）",
                    v9 and v9[0].get("gate_state") == "pending",
                    v9[0].get("gate_state") if v9 else "")
        ok &= check("此时还不可召回", "写小说" not in m9.render())
        ok &= check("带复核标记（缺时间依据）", bool(v9 and v9[0].get("needs_review")))
        with m9._mutation() as w9:
            recs9, _, _ = R.approve_pending(w9._view(), by="human")
            if recs9 is not None:
                w9._replace_all(recs9)
        ok &= check("人工放行后进入召回", "写小说" in m9.render())'''
s = s.replace(old, new, 1)

if "import memrec as R" not in s:
    # 找现有的 M / memrec 导入别名
    print("需要的导入：")
    for ln in s.split("\n")[:30]:
        if ln.startswith("import") or ln.startswith("from"):
            print("   ", ln)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("W9 断言已按新行为改写")
