"""第三层：嘴。

原版那几张：neutral 只有 15x11，屏幕上就是个点，看着像没有嘴；而且配色是酱红。
这里按放大后的 sprite 框重画一套我的：
    墨蓝紫描边（和睫毛同一支笔），里面是酒红渐变到珊瑚粉，舌头亮一点。

框中心 = 嘴线（master y 769 左右），说话时 figure.js 会把 happy 纵向压扁来张嘴，
所以 happy 要画成「张开的大笑」——压扁了正好变成闭着嘴的笑。

    python mouths.py   ->  schemes/yuyu/feat/*_mouth.png + blobs/mouth-review.png
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
MODEL = WHALE / "model.json"
OUT = WHALE / "schemes" / "yuyu" / "feat"
REVIEW = HERE.parent.parent / "blobs" / "mouth-review.png"

SS = 6
INK = (32, 24, 46)          # 描边：和睫毛一个色系
THROAT = (120, 34, 54)      # 口腔里面，越往下越亮
INNER = (206, 84, 96)
TONGUE = (255, 138, 150)
TONGUE_LIP = (255, 196, 200)
SHINE = (255, 236, 240)


def bez(p0, p1, p2, n=28):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / (n - 1) for i in range(n))]


def grad(size, top, bot):
    w, h = size
    g = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        k = y / max(1, h - 1)
        d.point((0, y), tuple(round(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    return g.resize(size, Image.BILINEAR).convert("RGBA")


def open_mouth(size, pts, tongue=None, shine=None, line=None):
    """张开的口：形状由 pts 给，填竖向渐变，底下贴一条舌头，外面描一圈墨。"""
    w, h = size
    S = SS
    mask = Image.new("L", (w * S, h * S), 0)
    md = ImageDraw.Draw(mask)
    md.polygon([(x * S, y * S) for x, y in pts], fill=255)
    body = grad((w * S, h * S), THROAT, INNER)
    body.putalpha(mask)

    if tongue:
        tm = Image.new("L", (w * S, h * S), 0)
        ImageDraw.Draw(tm).ellipse([v * S for v in tongue], fill=255)
        tm = Image.composite(tm, Image.new("L", tm.size, 0), mask)
        tm = tm.filter(ImageFilter.GaussianBlur(1.1 * S))
        body = Image.composite(Image.new("RGBA", body.size, TONGUE + (255,)), body, tm)

    if shine:
        sm = Image.new("L", (w * S, h * S), 0)
        ImageDraw.Draw(sm).ellipse([v * S for v in shine], fill=110)
        sm = sm.filter(ImageFilter.GaussianBlur(1.6 * S))
        sm = Image.composite(sm, Image.new("L", sm.size, 0), mask)
        body = Image.composite(Image.new("RGBA", body.size, SHINE + (255,)), body, sm)

    line = line or (w * 0.055)
    d = ImageDraw.Draw(body)
    d.line([(x * S, y * S) for x, y in pts] + [(pts[0][0] * S, pts[0][1] * S)],
           fill=INK + (255,), width=int(line * S), joint="curve")
    return body.resize((w, h), Image.LANCZOS)


def curved_mouth(size, pts, line, colour=INK, caps=True):
    w, h = size
    S = SS
    cv = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)
    d.line([(x * S, y * S) for x, y in pts], fill=colour + (255,), width=int(line * S), joint="curve")
    if caps:
        for x, y in (pts[0], pts[-1]):
            r = line * S / 2
            d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill=colour + (255,))
    return cv.resize((w, h), Image.LANCZOS)


def smile_pts(size, height=0.80, inset=0.07, lift=0.03):
    """张开的笑：上唇一条几乎直的线（两端微微上挑），下面是半圆——比两头尖的形状好看得多。
    竖直方向以画布中心为中线，说话时 figure.js 绕这个中心压扁。"""
    w, h = size
    x0, x1 = w * inset, w * (1 - inset)
    cx, rx = (x0 + x1) / 2, (x1 - x0) / 2
    top_y = h * (0.5 - height / 2)
    ry = h * height
    pts = bez((x0, top_y), (cx, top_y - h * lift), (x1, top_y))
    for i in range(1, 25):
        a = math.pi * i / 24
        pts.append((cx + rx * math.cos(a), top_y + ry * math.sin(a)))
    return pts, (cx - rx * 0.60, top_y + ry * 0.52,
                 cx + rx * 0.60, top_y + ry * 1.02)


def neutral(size):
    w, h = size
    pts = bez((w * .10, h * .26), (w * .5, h * .86), (w * .90, h * .26))
    return curved_mouth(size, pts, h * 0.34)


def sleep(size):
    w, h = size
    pts = bez((w * .22, h * .36), (w * .5, h * .74), (w * .78, h * .36))
    return curved_mouth(size, pts, h * 0.30)


def dizzy(size):
    w, h = size
    a = bez((w * .12, h * .42), (w * .30, h * .78), (w * .48, h * .46))
    b = bez((w * .48, h * .46), (w * .66, h * .16), (w * .86, h * .54))
    return curved_mouth(size, a + b[1:], h * 0.26)


def happy(size):
    pts, tongue = smile_pts(size, height=0.62, inset=0.04)
    return open_mouth(size, pts, tongue=tongue, shine=None)


def love(size):
    pts, tongue = smile_pts(size, height=0.70, inset=0.03)
    return open_mouth(size, pts, tongue=tongue)


def drag(size):
    w, h = size
    pts = [(w * .30, h * .16)]
    pts += bez((w * .30, h * .16), (w * .50, h * .06), (w * .70, h * .16))
    pts += bez((w * .70, h * .16), (w * .78, h * .52), (w * .50, h * .86))
    pts += bez((w * .50, h * .86), (w * .22, h * .52), (w * .30, h * .16))[1:]
    return open_mouth(size, pts,
                      tongue=(w * .32, h * .58, w * .68, h * .88),
                      shine=(w * .34, h * .20, w * .48, h * .30))


def surprised(size):
    w, h = size
    cx, cy, rx, ry = w * .5, h * .5, w * .30, h * .42
    S = SS
    mask = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(mask).ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
    body = grad((w * S, h * S), THROAT, INNER)
    body.putalpha(mask)
    tm = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(tm).ellipse([(cx - rx * .8) * S, (cy + ry * .35) * S,
                                (cx + rx * .8) * S, (cy + ry * .95) * S], fill=255)
    tm = tm.filter(ImageFilter.GaussianBlur(1.1 * S))
    tm = Image.composite(tm, Image.new("L", tm.size, 0), mask)
    body = Image.composite(Image.new("RGBA", body.size, TONGUE + (255,)), body, tm)
    d = ImageDraw.Draw(body)
    d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S],
              outline=INK + (255,), width=int(w * .055 * S))
    return body.resize((w, h), Image.LANCZOS)


DRAW = {
    "neutral_mouth": neutral,
    "happy_mouth": happy,
    "sleep_mouth": sleep,
    "drag_mouth": drag,
    "love_mouth": love,
    "dizzy_mouth": dizzy,
    "surprised_mouth": surprised,
}


def main() -> int:
    sprites = json.loads(MODEL.read_text(encoding="utf-8"))["feat"]["sprites"]
    OUT.mkdir(parents=True, exist_ok=True)

    cells = []
    for name, fn in DRAW.items():
        x0, y0, x1, y1 = sprites[name]
        im = fn((x1 - x0, y1 - y0))
        im.save(OUT / f"{name}.png")
        print(f"{name:16s} {(x1 - x0)}x{(y1 - y0)}")
        cells.append(im)

    # 审图：灰底上放大 6 倍排一行
    K = 6
    w = sum(c.width * K for c in cells) + 18 * (len(cells) - 1)
    h = max(c.height * K for c in cells)
    sheet = Image.new("RGBA", (w, h), (232, 214, 208, 255))
    x = 0
    for c in cells:
        sheet.alpha_composite(c.resize((c.width * K, c.height * K), Image.LANCZOS), (x, 0))
        x += c.width * K + 18
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(REVIEW)
    print("review", REVIEW, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
