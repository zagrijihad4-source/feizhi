import sqlite3
import time
import datetime

db = r"D:\Hermes work\feizhi-wechat-phone-bridge\state\events.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()

now_ms = int(time.time() * 1000)
print("now_ms =", now_ms, "=", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# events 表：按时间倒序
cur.execute("SELECT event_id, sender, posted_at_ms, state, reply, error, incoming_text, failure_count FROM events ORDER BY posted_at_ms DESC LIMIT 8")
print("\n=== events (latest 8) ===")
for r in cur.fetchall():
    eid, sender, ts, state, reply, err, txt, fc = r
    t = datetime.datetime.fromtimestamp(ts / 1000.0).strftime("%m-%d %H:%M:%S")
    print(f"  [{t}] state={state} fc={fc} sender={sender!r}")
    print(f"      in={txt!r}")
    if reply:
        print(f"      reply={reply[:80]!r}")
    if err:
        print(f"      ERROR={err[:120]!r}")

# conversation_messages：按时间倒序
cur.execute("SELECT message_id, role, text, sent_at_ms, source FROM conversation_messages ORDER BY sent_at_ms DESC LIMIT 10")
print("\n=== conversation_messages (latest 10) ===")
for r in cur.fetchall():
    mid, role, txt, ts, src = r
    t = datetime.datetime.fromtimestamp(ts / 1000.0).strftime("%m-%d %H:%M:%S")
    age_min = (now_ms - ts) / 60000.0
    print(f"  [{t}] age={age_min:.1f}min role={role} source={src}")
    print(f"      {txt[:100]!r}")

# 统计
cur.execute("SELECT source, COUNT(*) FROM conversation_messages GROUP BY source")
print("\n=== source breakdown ===")
for src, n in cur.fetchall():
    print(f"  {src}: {n}")

cur.execute("SELECT state, COUNT(*) FROM events GROUP BY state")
print("\n=== event state breakdown ===")
for st, n in cur.fetchall():
    print(f"  {st}: {n}")

con.close()
