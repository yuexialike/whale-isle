"""先看清楚现有那几张嘴巴图到底长什么样——为什么屏幕上像没有嘴。

打印每张的脸白底大小、alpha 范围、不透明像素的平均色，
再把它们按原尺寸拼一张放大图，肉眼对比。

    python probe_mouth.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
FEAT = WHALE / "schemes" / "yuyu" / "feat"
ORIG_FEAT = WHALE / "feat"
OUT = HERE.parent.parent / "blobs" / "mouth-src.png"

NAMES = ["neutral_mouth", "happy_mouth", "sleep_mouth", "drag_mouth",
         "love_mouth", "dizzy_mouth", "surprised_mouth"]


def stat(im: Image.Image) -> str:
    a = im.getchannel("A")
    box = a.point(lambda v: 255 if v > 8 else 0).getbbox()
    px = list(im.getdata())
    solid = [(r, g, b, aa) for r, g, b, aa in px if aa > 128]
    if solid:
        n = len(solid)
        avg = tuple(round(sum(c[i] for c in solid) / n) for i in range(3))
        darkest = min(solid, key=lambda c: c[0] + c[1] + c[2])[:3]
        brightest = max(solid, key=lambda c: c[0] + c[1] + c[2])[:3]
    else:
        avg = darkest = brightest = None
    return f"size={im.width}x{im.height} alphaBox={box} solid={len(solid)} avg={avg} dark={darkest} bright={brightest}"


def main() -> int:
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    boxes = model["feat"]["sprites"]
    cells = []
    for n in NAMES:
        for tag, d in (("yuyu", FEAT), ("原版", ORIG_FEAT)):
            p = d / f"{n}.png"
            if not p.exists():
                print(f"{n:16s} {tag} 缺 {p}")
                continue
            im = Image.open(p).convert("RGBA")
            print(f"{n:16s} {tag:3s} box={boxes.get(n)} {stat(im)}")
            # 垫一层灰，不然透明背景上看不见
            pad = Image.new("RGBA", (im.width + 8, im.height + 8), (120, 124, 140, 255))
            pad.alpha_composite(im, (4, 4))
            cells.append(pad)
    w = sum(c.width * 8 for c in cells) + 20 * (len(cells) - 1)
    h = max(c.height * 8 for c in cells)
    sheet = Image.new("RGBA", (w, h), (30, 34, 48, 255))
    x = 0
    for c in cells:
        sheet.alpha_composite(c.resize((c.width * 8, c.height * 8), Image.NEAREST), (x, 0))
        x += c.width * 8 + 20
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print("sheet", OUT, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
