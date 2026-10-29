import sqlite3
c=sqlite3.connect("state/context.sqlite3")
c.row_factory=sqlite3.Row
for r in c.execute("select * from messages order by rowid desc limit 12"):
    d=dict(r)
    print({k:d[k] for k in d})
