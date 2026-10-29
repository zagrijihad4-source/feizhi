import io, json
p = "tts_config.json"
d = json.loads(io.open(p, encoding="utf-8").read())
old = d["breeze"]["voice_id"]
d["breeze"]["voice_id"] = "voc_f6hmxqkrnj8e"
io.open(p, "w", encoding="utf-8", newline="\n").write(
    json.dumps(d, ensure_ascii=False, indent=2))
print("voice_id: %s -> %s" % (old, d["breeze"]["voice_id"]))
