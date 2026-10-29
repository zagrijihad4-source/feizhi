"""打断改口：队列里还有同一联系人的更新回复时，旧回复必须整条跳过。"""
import queue
import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

import autoreply

r = object.__new__(autoreply.AutoReplier)
r._send_q = queue.Queue()

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", got, "" if ok else "want " + str(want))


# 空队列：没有更新，正常发送
check("空队列", r._has_newer_for("wxid_a"), False)

r._send_q.put(("wxid_b", None, None, None, None, 2))
r._send_q.put(("wxid_a", None, None, None, None, 3))
check("有同一人更新", r._has_newer_for("wxid_a"), True)
check("只有别人的", r._has_newer_for("wxid_c"), False)
check("别人也在队列", r._has_newer_for("wxid_b"), True)

# 队列被取空后不应误判
r._send_q.get()
r._send_q.get()
check("取空后", r._has_newer_for("wxid_a"), False)

# superseded 不应被 recover_outbound 重新捞出来重发
import store as store_mod
import time

st = store_mod.ContextStore()
oid = st.enqueue_outbound("wxid_test_supersede", {"messages": [{"text": "过时的一句"}]})
st.mark_outbound(oid, "superseded", "被更新的入站消息替代")
before = st.outbound_stats()
st.recover_outbound()
after = st.outbound_stats()
check("superseded 保持不重发", before.get("superseded"), after.get("superseded"))
st._con.execute("delete from outbound where id = ?", (oid,))
st._con.commit()
print("清理测试记录 id =", oid)

print("\nFAILS =", fails)
sys.exit(0 if fails == 0 else 1)
