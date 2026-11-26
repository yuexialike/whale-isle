"""Redraw the whale's layers myself — flat colours, clean outlines, same canvas sizes.

月下 17:31：「可以。」(换我自己画的图层当皮肤)

做法：PIL 4 倍超采样后缩回来，位置/画布严格照抄 `tex/` 里同名文件的像素尺寸，
所以 model.json 的 box/grid 一个字不用改。
曲线走 Catmull-Rom 插值，点给少一点也能圆。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
OUT = WHALE / "schemes" / "yuyu" / "tex"
TEX = WHALE / "tex"

SS = 4  # supersampling


def catmull(pts, closed=True, steps=10):
    """把控制点串成平滑曲线上的密集点。"""
    n = len(pts)
    if n < 3:
        return list(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not closed:
        out.append(pts[-1])
    return out


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def blob(self, pts, fill=None, line=None, width=0.0, closed=True, steps=12):
        dense = catmull(pts, closed, steps)
        p = [(x * SS, y * SS) for x, y in dense]
        if fill:
            self.d.polygon(p, fill=fill)
        if line and width:
            loop = p + [p[0]] if closed else p
            wd = max(1, int(round(width * SS)))
            self.d.line(loop, fill=line, width=wd, joint="curve")
            if not closed:
                for pt in (loop[0], loop[-1]):
                    r = wd / 2
                    self.d.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=line)
        return self

    def ellipse(self, box, fill=None, line=None, width=0.0):
        b = [v * SS for v in box]
        self.d.ellipse(b, fill=fill, outline=line, width=max(1, int(width * SS)))
        return self

    def save(self, name: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        self.im.resize((self.w, self.h), Image.LANCZOS).save(OUT / name)


def size_of(name: str) -> tuple[int, int]:
    with Image.open(TEX / name) as im:
        return im.size


# 我的配色：深海蓝头发、偏白的皮肤、珊瑚粉腮红
HAIR = (94, 148, 216, 255)
HAIR_DARK = (66, 110, 176, 255)
HAIR_LIGHT = (176, 214, 246, 255)
SKIN = (255, 242, 236, 255)
SKIN_SHADE = (247, 218, 210, 255)
BLUSH = (255, 168, 168, 200)
LINE = (46, 56, 88, 255)


def draw_face() -> None:
    w, h = size_of("face.png")
    c = Canvas(w, h)
    cx = w / 2
    pts = [
        (cx, h * .03), (w * .78, h * .10), (w * .92, h * .30), (w * .93, h * .52),
        (w * .80, h * .78), (w * .64, h * .92), (cx, h * .97), (w * .36, h * .92),
        (w * .20, h * .78), (w * .07, h * .52), (w * .08, h * .30), (w * .22, h * .10),
    ]
    c.blob(pts, fill=SKIN, line=LINE, width=2.4)
    # 下巴的暖影
    c.ellipse([cx - w * .15, h * .86, cx + w * .15, h * .99], fill=SKIN_SHADE)
    # 腮红
    for fx in (.22, .78):
        c.ellipse([w * fx - w * .10, h * .55, w * fx + w * .10, h * .70], fill=BLUSH)
    c.save("face.png")


def draw_bangs() -> None:
    w, h = size_of("bangs.png")
    c = Canvas(w, h)
    cx = w / 2
    body = [
        (w * .04, h * .70), (w * .03, h * .34), (w * .13, h * .12), (w * .32, h * .02),
        (cx, h * .00), (w * .68, h * .02), (w * .87, h * .12), (w * .97, h * .34),
        (w * .96, h * .70),
        (w * .88, h * .56), (w * .80, h * .74),
        (w * .68, h * .50), (w * .58, h * .80),
        (w * .46, h * .52), (w * .36, h * .78),
        (w * .22, h * .54), (w * .12, h * .72),
    ]
    c.blob(body, fill=HAIR, line=LINE, width=2.6, steps=14)
    # 右侧压深（沿着右半边轮廓的一道）
    c.blob([(cx, h * .06), (w * .70, h * .05), (w * .86, h * .14), (w * .95, h * .34),
            (w * .94, h * .62), (w * .88, h * .56), (w * .80, h * .72),
            (w * .70, h * .48), (cx, h * .44)],
           fill=HAIR_DARK, steps=12)
    # 额头那圈高光
    c.blob([(w * .24, h * .34), (w * .38, h * .26), (w * .56, h * .24), (w * .66, h * .30),
            (w * .52, h * .40), (w * .34, h * .42)], fill=HAIR_LIGHT, steps=10)
    # 两缕亮丝
    c.blob([(w * .20, h * .40), (w * .24, h * .62), (w * .30, h * .42)],
           fill=HAIR_LIGHT, steps=8)
    c.save("bangs.png")


def draw_ahoge() -> None:
    w, h = size_of("ahoge.png")
    c = Canvas(w, h)
    # 一根打卷的呆毛：从右下起，往上绕一小圈再垂下来
    pts = [(w * .26, h * .97), (w * .30, h * .72), (w * .26, h * .44), (w * .34, h * .22),
           (w * .50, h * .08), (w * .66, h * .10), (w * .76, h * .26), (w * .74, h * .44),
           (w * .62, h * .54), (w * .52, h * .48), (w * .52, h * .34), (w * .60, h * .26),
           (w * .66, h * .30), (w * .62, h * .40), (w * .56, h * .40), (w * .56, h * .30),
           (w * .48, h * .28), (w * .44, h * .46), (w * .40, h * .70), (w * .36, h * .95)]
    c.blob(pts, fill=HAIR, line=LINE, width=2.2, closed=False, steps=12)
    c.save("ahoge.png")


def main() -> int:
    draw_face()
    draw_bangs()
    draw_ahoge()
    for n in ("face.png", "bangs.png", "ahoge.png"):
        print(n, (OUT / n).stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
