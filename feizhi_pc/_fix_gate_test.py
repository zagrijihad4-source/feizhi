import io
p = "_test_gate.py"
s = io.open(p, encoding="utf-8").read()

s = s.replace(
    '    view = mem._view()\n    rec = (view.get("events") or [])[-1]',
    '    view = mem._view()\n    rec = [r for r in view if r.get("text") == "<OWNER>要交材料"][0]', 1)

s = s.replace(
    '    view2 = mem2._view()\n    rec2 = (view2.get("events") or [])[-1]',
    '    view2 = mem2._view()\n    rec2 = [r for r in view2 if "辣椒炒肉" in str(r.get("text"))][0]', 1)

s = s.replace(
    '''    view4 = mem4._view()
    idx = len(view4["events"]) - 1
    view4["events"][idx]["archived"] = True''',
    '''    view4 = mem4._view()
    for r in view4:
        if r.get("text") == "<OWNER>去打球":
            r["archived"] = True''', 1)

s = s.replace(
    '''    view5["events"][-1]["gate_state"] = "eligible"''',
    '''    for r in view5:
        if r.get("text") == "<OWNER>去打球":
            r["gate_state"] = "eligible"''', 1)

s = s.replace('    after = recs[-1]', '    after = [r for r in recs if r.get("text") == "<OWNER>要交材料"][0]', 1)
s = s.replace('    check("放行后可召回", recs3[-1] in R.recallable(recs3))',
              '    check("放行后可召回", any(r["id"] == rec2["id"] for r in R.recallable(recs3)))', 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("测试已按 list 视图修正")
