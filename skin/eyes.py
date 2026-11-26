"""第二层：眼睛。

原版眼睛是四层叠的（见 eye_ref.py / figure.js paintOpenEye）：
    ball  眼白
    iris  虹膜（source-atop 裁进 ball）
    hl    两点高光，单独一层（配色的 eyeHighlights）
    lash  上睫毛 + 眼尾，绕眼心转、闭眼时压扁

我这一版：
  - 虹膜自己画：丁香紫到青蓝的竖渐变、深色描边、内圈打亮、竖瞳，底下一圈水光；
    外轮廓沿用原版 iris 的 alpha，保证裁进眼白时边界对得上。
  - 高光自己摆：大点偏左上，小点偏下，像水面反光。
  - 睫毛换成墨蓝紫，不用原版那个酱油红。

    python eyes.py  ->  schemes/yuyu/feat/{eyeL,eyeR}_{iris,hl,lash}.png  +  blobs/eye-review.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
SRC = WHALE / "tex"          # 原版贴图（iris 形状的参照）
SRC_FEAT = WHALE / "feat"    # 原版 feat 层
DST = WHALE / "schemes" / "yuyu" / "feat"
REVIEW = HERE.parent.parent / "blobs" / "eye-review.png"

SS = 4

EYES = ("eyeL", "eyeR")

# 虹膜：从上游的深靛到底下的水青
# 20:05 月下说「眼睛颜色太浅，上面一块太浅、下面太显，神态不强」→ 整体压深一档，
# 底下那一圈水光收住（原来冲到接近白），高光缩小，上眼皮的暗压得更实，瞳孔做清楚。
IRIS_TOP = (24, 44, 128)
IRIS_MID = (52, 116, 206)
IRIS_LOW = (132, 208, 246)
IRIS_RIM = (18, 28, 86)
GLOW = (198, 240, 255)
PUPIL = (10, 14, 48)
LASH_DARK = (26, 21, 44)
LASH_LIGHT = (62, 48, 96)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(size, stops) -> Image.Image:
    """竖渐变。stops = [(0..1, rgb), ...]"""
    w, h = size
    im = Image.new("RGB", (1, h))
    px = im.load()
    stops = sorted(stops)
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                px[0, y] = lerp(c0, c1, k)
                break
        else:
            px[0, y] = stops[-1][1]
    return im.resize((w, h), Image.NEAREST)


def make_iris(name: str) -> Image.Image:
    old = Image.open(SRC_FEAT / f"{name}_iris.png").convert("RGBA")
    w, h = old.size
    cw, ch = w * SS, h * SS
    # 原版 alpha 放大当形状：只在我这块画布内，边界跟 rig 对得上
    shape = old.getchannel("A").resize((cw, ch), Image.LANCZOS)

    body = gradient((cw, ch), [
        (0.00, IRIS_TOP),
        (0.32, (40, 88, 176)),
        (0.64, (64, 148, 220)),
        (1.00, IRIS_LOW),
    ]).convert("RGBA")

    # 虹膜边上一圈更深的描边
    inner = shape.filter(ImageFilter.GaussianBlur(1.6 * SS)).point(lambda v: 255 if v > 150 else 0)
    inner = inner.filter(ImageFilter.MinFilter(3 * SS + 1)).filter(ImageFilter.GaussianBlur(0.6 * SS))
    rim = ImageChops.subtract(shape, inner)
    body = Image.composite(Image.new("RGBA", (cw, ch), IRIS_RIM + (255,)), body, rim)

    # 下半圈的水光：一个大而虚的椭圆（20:05 两个硬边椭圆还看得出团，改成一个）
    glow = Image.new("L", (cw, ch), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cw * 0.10, ch * 0.52, cw * 0.90, ch * 1.04], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(5.0 * SS))
    glow = ImageChops.multiply(glow, inner)
    body = Image.composite(Image.new("RGBA", (cw, ch), GLOW + (255,)), body, glow)

    # 上眼皮压下来那点暗，眼珠才不飘（20:05 压得更实、更宽，眼神才立得住）
    lid = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(lid).ellipse([-cw * 0.2, -ch * 0.58, cw * 1.2, ch * 0.20], fill=150)
    lid = lid.filter(ImageFilter.GaussianBlur(3 * SS))
    lid = ImageChops.multiply(lid, inner)
    body = Image.composite(Image.new("RGBA", (cw, ch), (22, 34, 104, 255)), body, lid)

    # 竖瞳：中间偏上一点，上下细（20:05 做清楚些，原来淡得像没有瞳孔）
    pupil = Image.new("L", (cw, ch), 0)
    pw, ph = cw * 0.185, ch * 0.300
    cx, cy = cw * 0.50, ch * 0.50
    ImageDraw.Draw(pupil).ellipse([cx - pw, cy - ph, cx + pw, cy + ph], fill=255)
    pupil = pupil.filter(ImageFilter.GaussianBlur(0.8 * SS))
    pupil = ImageChops.multiply(pupil, inner)
    body = Image.composite(Image.new("RGBA", (cw, ch), PUPIL + (255,)), body, pupil)

    # 瞳孔下缘一道很浅的反光，别让瞳孔变成黑洞
    under = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(under).ellipse([cx - pw * 0.80, cy + ph * 0.44, cx + pw * 0.80, cy + ph * 0.82], fill=96)
    under = under.filter(ImageFilter.GaussianBlur(2 * SS))
    under = ImageChops.multiply(under, inner)
    body = Image.composite(Image.new("RGBA", (cw, ch), (80, 148, 222, 255)), body, under)

    body.putalpha(shape)
    return body.resize((w, h), Image.LANCZOS)


def make_hl(name: str) -> Image.Image:
    old = Image.open(SRC_FEAT / f"{name}_hl.png").convert("RGBA")
    w, h = old.size
    cw, ch = w * SS, h * SS
    cv = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    # 大点：虹膜左上一颗，小点：右下，压扁一点（位置按原版 hl 画布的实际落点摆）
    # 20:05 高光缩小、下移一点点：原来那颗太大，把虹膜上半块盖成了白的。
    r = cw * 0.155
    bx, by = cw * 0.345, ch * 0.255
    d.ellipse([bx - r, by - r, bx + r, by + r], fill=(255, 255, 255, 255))
    r2w, r2h = cw * 0.075, ch * 0.105
    cx2, cy2 = cw * 0.655, ch * 0.575
    d.ellipse([cx2 - r2w, cy2 - r2h, cx2 + r2w, cy2 + r2h], fill=(255, 255, 255, 170))
    cv = cv.filter(ImageFilter.GaussianBlur(0.4 * SS))
    return cv.resize((w, h), Image.LANCZOS)


def make_lash(name: str) -> Image.Image:
    old = Image.open(SRC_FEAT / f"{name}_lash.png").convert("RGBA")
    w, h = old.size
    cw, ch = w * SS, h * SS
    big = old.resize((cw, ch), Image.LANCZOS)
    a = big.getchannel("A")
    # 用原版明度当深浅：亮的地方留浅，暗的地方压深
    lum = big.convert("L")
    lo, hi = lum.getextrema()
    span = max(1, hi - lo)

    ramp = gradient((cw, ch), [(0.0, LASH_LIGHT), (1.0, LASH_DARK)]).convert("RGBA")
    lum_big = lum.point(lambda v: 255 - int((v - lo) * 255 / span))
    luma = Image.merge("RGBA", (lum_big, lum_big, lum_big, a))
    out = Image.composite(ramp, Image.new("RGBA", (cw, ch), LASH_LIGHT + (255,)), a.point(lambda v: 255 if v > 8 else 0))
    out = Image.composite(Image.new("RGBA", (cw, ch), LASH_DARK + (255,)), out,
                          luma.getchannel("R").point(lambda v: v))
    out.putalpha(a)
    return out.resize((w, h), Image.LANCZOS)


def composite(k: str, eyes: dict, folder: Path) -> Image.Image:
    """按 figure.js 的静止状态拼一只完整的眼睛，方便看效果。"""
    e = eyes[k]
    def load(n):
        p = folder / f"{k}_{n}.png"
        return Image.open(p).convert("RGBA")
    ball, iris, hl, lash = load("ball"), load("iris"), load("hl"), load("lash")
    bx, by = e["ball"][0], e["ball"][1]
    pads = (24, 24)
    cv = Image.new("RGBA", (ball.width + pads[0] * 2, ball.height + pads[1] * 2), (0, 0, 0, 0))
    cv.alpha_composite(ball, pads)
    cv.alpha_composite(iris, (pads[0] + e["iris"][0] - bx, pads[1] + e["iris"][1] - by))
    hx = pads[0] + (e["hl"][0] + e["hl"][2] - 2 * bx - hl.width) // 2
    hy = pads[1] + (e["hl"][1] + e["hl"][3] - 2 * by - hl.height) // 2
    cv.alpha_composite(hl, (hx, hy))
    cv.alpha_composite(lash, (pads[0] + e["lash"][0] - bx, pads[1] + e["lash"][1] - by))
    return cv


def main() -> int:
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    eyes = model["feat"]["eyes"]
    DST.mkdir(parents=True, exist_ok=True)

    for k in EYES:
        make_iris(k).save(DST / f"{k}_iris.png")
        make_hl(k).save(DST / f"{k}_hl.png")
        make_lash(k).save(DST / f"{k}_lash.png")
        print("wrote", k)

    # 审图：左 = 原版，右 = 我的
    cells = []
    for k in EYES:
        cells.append((f"{k} old", composite(k, eyes, SRC_FEAT)))
        cells.append((f"{k} new", composite(k, eyes, DST)))
    S = 3
    cells = [(n, c.resize((c.width * S, c.height * S), Image.LANCZOS)) for n, c in cells]
    width = sum(c.width for _, c in cells) + 24 * (len(cells) - 1)
    height = max(c.height for _, c in cells)
    sheet = Image.new("RGBA", (width, height), (38, 44, 62, 255))
    x = 0
    for _, c in cells:
        sheet.alpha_composite(c, (x, 0))
        x += c.width + 24
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(REVIEW)
    print("review", REVIEW, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
