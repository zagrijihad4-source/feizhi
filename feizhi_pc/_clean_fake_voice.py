import store

s = store.ContextStore()
q = "select count(*) from messages where text like ?"
n = s._con.execute(q, ("%唱完了啊%",)).fetchone()[0]
print("待清理:", n)
s._con.execute("delete from messages where text like ?", ("%唱完了啊%",))
s._con.commit()
m = s._con.execute(q, ("%唱完了啊%",)).fetchone()[0]
print("已删除，剩余:", m)
print("--- 最新 4 条 ---")
for r in s._con.execute("select id, role, substr(text,1,40) from messages order by id desc limit 4"):
    print(tuple(r))
