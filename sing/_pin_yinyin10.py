import io
p = "rvc_cover.py"
s = io.open(p, encoding="utf-8").read()
old = 'ap.add_argument("--model", default="yinyin.pth")'
assert s.count(old) == 1
new = ('# ★ 2026-10-29 定版：统一用 yinyin10（最后一次训练的模型，2026-10-24）。\n'
       '   之前默认 yinyin.pth 是最早那版，音色明显不对。其余模型保留供报告对比，别删。\n'
       '   index-rate 保持 0：索引会把音素换成检索集里的，音色变"平均值"且容易唱错字。\n'
       'ap.add_argument("--model", default="yinyin10.pth")')
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("rvc_cover.py 默认模型 -> yinyin10.pth")
