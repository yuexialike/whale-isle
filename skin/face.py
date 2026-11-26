"""我自己那张脸——按月下 18:13 的说法：脸型就用现在这个圆脸，别自己另捏一个。

所以轮廓直接取原版 face.png 的 alpha（一个像素都不改），
我只管这一层里的皮、色、腮红、轮廓线和下巴那根线。

画布尺寸和原版严格一样，rig 的 6x6 grid 才不会拉歪。

    python face.py   ->  schemes/yuyu/tex/face.png  +  blobs/face-review.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
TEX = WHALE / "tex"
OUT = WHALE / "schemes" / "yuyu" / "tex" / "face.png"
REVIEW = HERE.parent.parent / "blobs" / "face-review.png"

SS = 4

# 我的皮：暖一点、粉一点，别是那种塑料白
SKIN = (255, 245, 241)
SKIN_DEEP = (253, 228, 221)
SKIN_SHADOW = (250, 219, 212)
BLUSH = (255, 158, 156)
LINE = (198, 146, 142)      # 下巴那根线
OUTLINE = (214, 168, 162)   # 脸的轮廓，比皮肤深一点点就够


def solid(size, rgb):
    return Image.new("RGB", size, rgb)


def scaled(pts, cx, cy, k):
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]


def bbox_pts(x0, y0, bw, bh):
    """包围盒的四个角绕着中心缩一点，用来当皮肤内侧的椭圆——用多边形近似就够。"""
    import math
    cx, cy = x0 + bw / 2, y0 + bh / 2
    return [(cx + math.cos(a) * bw * 0.5, cy + math.sin(a) * bh * 0.5)
            for a in [i * math.pi / 24 for i in range(48)]]


def main() -> int:
    orig = Image.open(TEX / "face.png").convert("RGBA")
    W, H = orig.size
    a0 = orig.getchannel("A")
    x0, y0, x1, y1 = a0.point(lambda v: 255 if v > 10 else 0).getbbox()
    bw, bh = x1 - x0, y1 - y0
    cx, cy = x0 + bw / 2, y0 + bh / 2

    cw, ch = W * SS, H * SS
    # 1) 轮廓：原版的 alpha，直接放大，形状一点不动
    outer = a0.resize((cw, ch), Image.LANCZOS)

    # 2) 皮肤：边上深、中间亮
    inner_pts = scaled(bbox_pts(x0 * SS, y0 * SS, bw * SS, bh * SS), cx * SS, cy * SS, 0.72)
    inner = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(inner).polygon(inner_pts, fill=255)
    inner = inner.filter(ImageFilter.GaussianBlur(7 * SS))
    skin = Image.composite(solid((cw, ch), SKIN), solid((cw, ch), SKIN_DEEP), inner)

    # 3) 脸颊下沿压一点点阴影，脸才鼓
    shade = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(shade).ellipse(
        [cx * SS - bw * 0.62 * SS, cy * SS - bh * 0.10 * SS,
         cx * SS + bw * 0.62 * SS, cy * SS + bh * 0.95 * SS],
        fill=55,
    )
    shade = shade.filter(ImageFilter.GaussianBlur(14 * SS))
    shade = ImageChops.multiply(shade, outer)
    skin = Image.composite(solid((cw, ch), SKIN_SHADOW), skin, shade)

    face = skin.convert("RGBA")
    face.putalpha(outer)

    # 4) 腮红：两团，各贴在自己那只眼睛下面，远侧那边透视压窄一点
    blush = Image.new("L", (cw, ch), 0)
    bd = ImageDraw.Draw(blush)
    # 位置是对着 model.json 里两只眼睛的 ball 框算的：eyeL 中心 x=0.360、eyeR x=0.875，
    # 眼球下沿 y≈0.79 —— 腮红就贴在这条线下面一点，别往外侧跑（18:54 月下指的就是这个）。
    for fx, rx in ((0.352, 0.088), (0.872, 0.058)):
        ex, ey = (x0 + fx * bw) * SS, (y0 + 0.812 * bh) * SS
        rrx, rry = bw * rx * SS, bh * 0.042 * SS
        bd.ellipse([ex - rrx, ey - rry, ex + rrx, ey + rry], fill=100)
    blush = blush.filter(ImageFilter.GaussianBlur(4.5 * SS))
    blush = ImageChops.multiply(blush, outer)
    face = Image.composite(solid((cw, ch), BLUSH).convert("RGBA"), face, blush)

    # 5) 一圈轮廓：沿着原版 alpha 的边描一道暖褐的细边
    edge = ImageChops.subtract(outer, outer.filter(ImageFilter.MinFilter(int(2.4 * SS) * 2 + 1)))
    edge = edge.filter(ImageFilter.GaussianBlur(0.9 * SS)).point(lambda v: int(v * 0.6))
    face = Image.composite(solid((cw, ch), OUTLINE).convert("RGBA"), face, edge)

    # 6) 下巴那根线：只走下半圈，比轮廓重一点
    half = Image.new("L", (cw, ch), 0)
    hd = ImageDraw.Draw(half)
    top = int((cy + bh * 0.12) * SS)
    hd.rectangle([0, top, cw, ch], fill=255)
    half = half.filter(ImageFilter.GaussianBlur(6 * SS))
    low = ImageChops.multiply(edge, half)
    face = Image.composite(solid((cw, ch), LINE).convert("RGBA"), face, low)

    face = face.resize((W, H), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    face.save(OUT)

    # 7) 审图：原版 / 我的 / 和现有刘海呆毛拼一起
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    box = {p["id"]: p["box"] for p in model["parts"] if p["id"] in ("face", "bangs", "ahoge")}
    S = 3.0
    UNIT = 256

    def composite(layers) -> Image.Image:
        cv = Image.new("RGBA", (int(UNIT * S), int(UNIT * S)), (0, 0, 0, 0))
        for name in layers:
            src = OUT if name == "face" else WHALE / "schemes" / "yuyu" / "tex" / f"{name}.png"
            x, y, w, h = box[name]
            im = Image.open(src).convert("RGBA")
            im = im.resize((max(1, int(w * S)), max(1, int(h * S))), Image.LANCZOS)
            cv.alpha_composite(im, (int(x * S), int(y * S)))
        return cv

    full = composite(["face", "bangs", "ahoge"])
    crop = (int(72 * S), int(16 * S), int(200 * S), int(162 * S))
    head = full.crop(crop).resize(((crop[2] - crop[0]) * 2, (crop[3] - crop[1]) * 2), Image.LANCZOS)
    alone = face.resize((face.width * 3, face.height * 3), Image.LANCZOS)
    o = orig.resize((W * 3, H * 3), Image.LANCZOS)
    panels = [o, alone, head]
    width = sum(p.width for p in panels) + 32 * (len(panels) - 1)
    height = max(p.height for p in panels)
    sheet = Image.new("RGBA", (width, height), (26, 30, 44, 255))
    x = 0
    for p in panels:
        sheet.alpha_composite(p, (x, 0))
        x += p.width + 32
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(REVIEW)
    print("face", (W, H), "->", OUT)
    print("review", REVIEW, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
