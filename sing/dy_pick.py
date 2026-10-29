"""Pick a training subset from posts.json.

RVC does not need every second of audio; 15-25 minutes of clean singing beats
3 hours of noisy clips and keeps each epoch short. Score clips by how likely
they are to be a clean vocal take, then take a year-balanced slice.

usage: python dy_pick.py [count] [out_file]
"""
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(r"<PROJECT_ROOT>\sing")
POSTS = ROOT / "douyin" / "posts.json"

count = int(sys.argv[1]) if len(sys.argv) > 1 else 70
out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "douyin" / "pick.txt"

STRONG = ["清唱", "无伴奏", "干声", "清声", "纯人声"]
WEAK = ["翻唱", "弹唱", "cover", "原声"]

rows = json.loads(POSTS.read_text(encoding="utf8"))
scored = []
for r in rows:
    if not r.get("play"):
        continue
    dur = (r.get("duration_ms") or 0) / 1000.0
    if not (14.0 <= dur <= 50.0):
        continue
    text = (r.get("desc") or "") + " " + (r.get("music") or "")
    s = 0.0
    s += 3.0 * sum(1 for k in STRONG if k in text)
    s += 1.0 * sum(1 for k in WEAK if k in text)
    # a clip that is long enough to hold a phrase but not a whole song
    s += 1.0 if 18.0 <= dur <= 40.0 else 0.0
    y = int(time.strftime("%Y", time.localtime(r["create_time"]))) if r.get("create_time") else 0
    scored.append((s, y, dur, r))

scored.sort(key=lambda t: (-t[0], -t[1]))

# year-balanced: no single year may dominate, so the model sees every era
quota = max(count // 6, 6)
buckets = {}
picked = []
for s, y, dur, r in scored:
    if len(picked) >= count:
        break
    if buckets.get(y, 0) >= quota and sum(buckets.values()) < count:
        continue
    buckets[y] = buckets.get(y, 0) + 1
    picked.append((s, y, dur, r))
for s, y, dur, r in scored:
    if len(picked) >= count:
        break
    if r not in [p[3] for p in picked]:
        picked.append((s, y, dur, r))

lines = [p[3]["aweme_id"] for p in picked]
out.write_text("\n".join(lines), encoding="utf8")

print("picked %d clips, %.1f min total" % (len(lines), sum(p[2] for p in picked) / 60.0))
print("by year:", dict(sorted(buckets.items())))
for s, y, dur, r in picked[:20]:
    tag = "清唱" if "清唱" in (r["desc"] + r["music"]) else "   "
    print("  %s %d score=%.0f %4.1fs %s | %s" % (tag, y, s, dur, r["aweme_id"], r["desc"][:44]))
print("-> %s" % out)
