import io
p = "_make_avatar.py"
s = io.open(p, encoding="utf-8").read()

old = s[s.index('PROMPT = ('):s.index(')\n\n\ndef main')+1]
new = '''PROMPT = (
    "chibi anime illustration, super-deformed cute style, "
    "one girl head and shoulders only, oversized round head filling the upper square area "
    "of a vertical canvas, "
    "long crimson red hair spilling past her shoulders, soft glossy highlights, "
    "a few loose strands falling across her forehead, "
    "huge round glossy eyes with bright catchlights, calm slightly aloof gaze looking straight "
    "at the viewer, tiny suppressed smile at the corner of her mouth, "
    "round soft blushed cheeks, small nose, small closed mouth, "
    "wearing a cream cotton shirt with one small smear of ultramarine paint near the collar, "
    "soft window daylight from the upper left with cool faint fill on the right, "
    "gentle shadow across one cheek, "
    "flat cel shading with smooth gradient falloff, clean rounded outlines, "
    "muted palette of cream and soft grey with crimson red and ultramarine as the only accents, "
    "plain light background, generous empty margin around the head"
)'''
s = s.replace(old, new, 1)

old2 = '''    side = int(w * 0.96)            # 798，几乎满宽
    left = (w - side) // 2
    top = int(h * 0.048)            # 60，头顶留一点呼吸'''
new2 = '''    # 像素实测这张 832x1248：人物 bbox y130..1072，头顶 y≈130、下巴 y≈890、
    # 脸最宽处约 786px。正方形边长必须 ≥ 头宽，所以直接用满宽 832，
    # 纵向从 y≈100 起，正好含头顶留白 + 整个下巴。
    side = w
    left = 0
    top = int(h * 0.080)'''
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("prompt 改成长红发，裁剪按实测边界")
