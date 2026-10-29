import io
p = "sing.py"
s = io.open(p, encoding="utf-8").read()
old = '''DELIVERED = {
    "sakura_final": "樱花树下的约定",
    "lunxian_final": "沦陷",
}'''
assert s.count(old) == 1
new = '''DELIVERED = {
    "sakura_final": "樱花树下的约定",
    "lunxian_final": "沦陷",
    # 2026-10-29 新做：他在微信里点名要的这首
    "yua_final": "雨爱",
}'''
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("曲库已加入《雨爱》")
