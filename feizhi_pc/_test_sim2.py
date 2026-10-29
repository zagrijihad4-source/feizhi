import json, urllib.request

def post(path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:8799" + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))

post("/api/reset", {"relation": "stranger"})
for t in ("你是谁", "帮我上班", "你他妈是自动回复不", "唱个歌我听听"):
    d = post("/api/chat", {"relation": "stranger", "text": t})
    ms = d.get("messages", [])
    print("我：%s   （她 %d 条）" % (t, len(ms)))
    for i, m in enumerate(ms, 1):
        print("   %d. %s" % (i, m))
    print()
