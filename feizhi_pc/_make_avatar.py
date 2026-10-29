# -*- coding: utf-8 -*-
"""用项目自己的 synapse 线路给绯栀出一张 Q 版头像。

为什么不用 dsh 的 generate_image：那条线（aistarslab）积分不足，
而且网关声明支持的其他模型在这条线路上直接回「当前线路不支持该模型」。
imagegen.py 的 synapse 是配置里标注的「现用主线路」，额度独立。

synapse 只吃 832x1248（2:3）竖图 —— 传别的尺寸会 HTTP 400。
所以先出 2:3，再把中间裁成正方形当头像。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import imagegen  # noqa: E402

# Q 版头像：主体在画面上部，头占满宽度，下面留白方便裁方。
PROMPT = (
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
)


def main() -> int:
    print("provider:", imagegen.load_config().get("provider"))
    out = imagegen.generate(PROMPT, use_ref=False)
    if not out:
        print("生成失败")
        return 1
    print("OUT:", out, out.stat().st_size, "bytes")
    try:
        from PIL import Image
    except ImportError:
        print("（没有 PIL，跳过裁剪，保留 2:3 原图）")
        return 0
    im = Image.open(out)
    w, h = im.size
    print("原尺寸:", w, h)
    # 这张 832x1248 里人物位置：头顶 ≈ y110、下巴 ≈ y790、头宽 ≈ 730。
    # 头像要含整个头 + 一点领口，所以边长取到接近满宽，纵向从上边缘下方一点开始。
    # 像素实测这张 832x1248：人物 bbox y130..1072，头顶 y≈130、下巴 y≈890、
    # 脸最宽处约 786px。正方形边长必须 ≥ 头宽，所以直接用满宽 832，
    # 纵向从 y≈100 起，正好含头顶留白 + 整个下巴。
    side = w
    left = 0
    top = int(h * 0.080)
    sq = im.crop((left, top, left + side, top + side)).resize((640, 640), Image.LANCZOS)
    dst = out.with_name(out.stem + "_avatar.png")
    sq.save(dst, "PNG")
    print("头像:", dst, dst.stat().st_size, "bytes  %dx%d" % sq.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
