import sys
sys.path.insert(0, ".")
import memrec as R

batch = [{"id": 456, "time": 1792480000, "role": "user", "text": "辣椒炒肉"}]
cases = [
    ("fact", "<OWNER>中午吃的是辣椒炒肉"),
    ("event", "绯栀追问<OWNER>中午吃了没，<OWNER>答吃了辣椒炒肉"),
    ("event", "<OWNER>早上喝了杯豆浆"),
    ("fact", "<OWNER>晚上不吃饭"),
    ("event", "<OWNER>昨天吃了辣椒炒肉"),
]
for kind, text in cases:
    rec = {"kind": kind, "text": text, "certainty": "high", "source_msg_ids": [456]}
    try:
        norm, notes = R.validate(dict(rec), batch)
    except Exception as e:
        print("%-46s 抛异常 %s" % (text, e)); continue
    print("原: %s" % text)
    print("  规范后: %s" % norm.get("text"))
    print("  event_time=%r time_basis=%r time_raw=%r  needs_review=%s quarantined=%s"
          % (norm.get("event_time"), norm.get("time_basis"), norm.get("time_raw"),
             norm.get("needs_review"), norm.get("quarantined")))
    if notes:
        print("  notes: %s" % "; ".join(notes))
    print()
