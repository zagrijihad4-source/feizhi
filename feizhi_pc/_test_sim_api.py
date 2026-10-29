import json, urllib.request

def post(path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:8799" + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))

post("/api/reset", {"relation": "stranger"})
for t in ("你是谁", "帮我上班", "唱个歌我听听"):
    d = post("/api/chat", {"relation": "stranger", "text": t})
    print("我：%s" % t)
    for m in d.get("messages", []):
        print("   她：%s" % m)
    print()
