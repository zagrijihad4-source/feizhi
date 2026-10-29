import sqlite3
import sys

db = r"D:\Hermes work\feizhi-wechat-phone-bridge\state\events.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)

for t in tables:
    try:
        cur.execute('SELECT COUNT(*) FROM "%s"' % t)
        n = cur.fetchone()[0]
        cur.execute('PRAGMA table_info("%s")' % t)
        cols = [r[1] for r in cur.fetchall()]
        print("  %s: rows=%s cols=%s" % (t, n, cols))
    except Exception as e:
        print("  %s: ERR %s" % (t, e))

# 看每个表最新几行
for t in tables:
    try:
        cur.execute('PRAGMA table_info("%s")' % t)
        cols = [r[1] for r in cur.fetchall()]
        if not cols:
            continue
        order = None
        for cand in ("id", "rowid", "ts", "timestamp", "created_at"):
            if cand in cols:
                order = cand
                break
        q = 'SELECT * FROM "%s"' % t
        if order:
            q += ' ORDER BY "%s" DESC' % order
        q += " LIMIT 3"
        cur.execute(q)
        rows = cur.fetchall()
        print("\n=== LATEST in %s ===" % t)
        for r in rows:
            d = dict(zip(cols, r))
            s = str(d)
            print("  " + (s[:400] if len(s) > 400 else s))
    except Exception as e:
        print("latest %s ERR %s" % (t, e))

con.close()
