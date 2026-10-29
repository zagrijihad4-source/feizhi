import io
p = "memory.py"
s = io.open(p, encoding="utf-8").read()

old = '''            # ★ 闸门状态：现有抽取链路尚未接入来源闸门，
            #   这里显式标 legacy 表示"旧链路、未过闸门但按历史行为放行"。
            #   接入 v1.3 闸门后，这里必须改成 pending（等闸门放行）或 eligible（已过闸门），
            #   绝不能再继续用 legacy。
            nf, qf, pf, ffails = work._ingest("facts", facts, batch,
                                              gate_state="legacy")
            ne, qe, pe, efails = work._ingest("events", events, batch,
                                              gate_state="legacy")'''
assert s.count(old) == 1
new = '''            # ★★ 闸门接线（2026-10-28）：新写入一律 pending，再由 approve_pending
            #   做自动审核。旧代码这里硬编码 legacy（注释里作者自己也写着"接入后必须
            #   改成 pending"），等于让闸门整套机制空转 —— pending 不召回、promote
            #   矩阵、来源校验全部绕开，模型编的记忆落地即进 prompt。
            #   实测缺陷：原文只有「辣椒炒肉」，模型写成「<OWNER>中午吃的是辣椒炒肉」，
            #   几天后她拿这句当事实问「你中午不是吃的辣椒炒肉嘛」。
            nf, qf, pf, ffails = work._ingest("facts", facts, batch,
                                              gate_state="pending")
            ne, qe, pe, efails = work._ingest("events", events, batch,
                                              gate_state="pending")
            # 自动放行：只有完全干净的记录能立刻变 eligible，
            # 带复核标记（时段词/日期冲突/多相对词…）的留在 pending 等人看。
            # 这样既不会让她"失忆"，也不会让编出来的东西直接开口说话。
            _appr, _anotes, _asum = R.approve_pending(work._view(), by="auto")
            if _appr is not None:
                work._replace_all(_appr)
                LOG.info("闸门自动放行 %d 条；留 pending %d 条",
                         len(_asum["approved"]), len(_asum["kept"]))
            elif _asum["kept"]:
                LOG.info("闸门：%d 条留在 pending 待复核", len(_asum["kept"]))'''
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("闸门已接 pending + 自动放行")
