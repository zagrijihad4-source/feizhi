import io
p = "life.py"
s = io.open(p, encoding="utf-8").read()
old_mood = '''                                 "since": time.strftime("%Y-%m-%d %H:%M")}'''
new_mood = '''                                 "since": time.strftime("%Y-%m-%d %H:%M",
                                                         time.localtime(now))}'''
assert s.count(old_mood) == 1, s.count(old_mood)
s = s.replace(old_mood, new_mood)
old_tick = '''        self.data["last_tick"] = time.strftime("%Y-%m-%d %H:%M")
        self.save()'''
new_tick = '''        # 用传进来的 now 而不是真实时钟：补算历史某一天的推进时才不会错位
        self.data["last_tick"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
        self.save()'''
assert s.count(old_tick) == 1
s = s.replace(old_tick, new_tick)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched")
