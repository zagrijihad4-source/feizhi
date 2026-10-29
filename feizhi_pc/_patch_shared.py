import io, json
from pathlib import Path

p = "life.py"
s = io.open(p, encoding="utf-8").read()

old_sig = """    def __init__(self, path: Path | str = DEFAULT_PATH,
                 private_path: Path | str | None = None,
                 write_shared: bool = True):"""
new_sig = """    def __init__(self, path: Path | str = DEFAULT_PATH,
                 private_path: Path | str | None = None,
                 write_shared: bool = True,
                 keep_private_keys: bool = True):"""
assert s.count(old_sig) == 1
s = s.replace(old_sig, new_sig, 1)

old_doc = """        self.path = Path(path)
        self.private_path = Path(private_path) if private_path else None
        self.write_shared = bool(write_shared)
        self.data = self._load()"""
new_doc = """        self.path = Path(path)
        self.private_path = Path(private_path) if private_path else None
        self.write_shared = bool(write_shared)
        # keep_private_keys=False：只有共享层、没有私有层时（self_life()），
        # 落盘只写 SHARED_KEYS。否则共享文件里会寄生 shared/influences/
        # open_loops 三个空壳，谁哪天直接读它就会当成"她没有任何未了结的事"。
        self.keep_private_keys = bool(keep_private_keys)
        self.data = self._load()"""
assert s.count(old_doc) == 1
s = s.replace(old_doc, new_doc, 1)

old_save = """    def save(self) -> None:
        if not self.private_path:
            self._write(self.path, self.data)
            return"""
new_save = """    def save(self) -> None:
        if not self.private_path:
            obj = self.data if self.keep_private_keys else {
                k: self.data.get(k) for k in self.SHARED_KEYS}
            self._write(self.path, obj)
            return"""
assert s.count(old_save) == 1
s = s.replace(old_save, new_save, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("life.py 已加 keep_private_keys")

# peer_state.self_life() 用上它
p2 = "peer_state.py"
s2 = io.open(p2, encoding="utf-8").read()
old = "    return FeizhiLife(SELF_PATH)"
new = "    return FeizhiLife(SELF_PATH, keep_private_keys=False)"
assert s2.count(old) == 1
s2 = s2.replace(old, new, 1)
io.open(p2, "w", encoding="utf-8", newline="\n").write(s2)
print("peer_state.py self_life() 已收紧")

# 清掉共享文件里的寄生空壳
f = Path("state/feizhi_self.json")
d = json.loads(f.read_text(encoding="utf-8"))
keep = {k: d[k] for k in ("projects", "mood", "last_tick") if k in d}
f.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
print("feizhi_self.json 清理后字段:", list(keep))
