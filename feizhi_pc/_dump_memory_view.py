"""只读导出：把生产记忆完整视图 dump 到文件，供人工核对与反思层设计。

不写任何状态。安全。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402

OUT = Path(__file__).resolve().parent / "eval" / "_dump_view.txt"

m = FeizhiMemory()
recs = m._view()
live = R.recallable(recs)
facts = [x for x in live if x.get("kind") != "event"]
events = [x for x in live if x.get("kind") == "event"]
allrec = recs

lines = []
lines.append("stats: %s" % (m.stats(),))
lines.append("total_records=%d recallable=%d facts=%d events=%d"
             % (len(allrec), len(live), len(facts), len(events)))
lines.append("")
lines.append("=== render_existing() ===")
lines.append(m.render_existing())
lines.append("")
lines.append("=== 全部记录（含归档/隔离，逐字段）===")
for i, x in enumerate(allrec):
    lines.append("[%03d] id=%s kind=%s gate=%s cert=%s ev=%s review=%s arch=%s quar=%s"
                 % (i, x.get("id"), x.get("kind"), x.get("gate_state"),
                    x.get("certainty"), x.get("event_time"),
                    bool(x.get("needs_review")), bool(x.get("archived")),
                    bool(x.get("quarantined"))))
    lines.append("      text=%s" % x.get("text"))
    lines.append("      src=%s time_raw=%r basis=%s"
                 % (x.get("source_msg_ids"), x.get("time_raw"), x.get("time_basis")))

OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote %s (%d bytes)" % (OUT, OUT.stat().st_size))
