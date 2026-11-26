"""第二条路：形状不动，只把原图的头发换成我的配色。

月下 17:31「可以」，17:30 说过「尽量秒」——这条路就是为了快：像素级重上色，
box/grid 一个都不碰，形状还是现在这个形状。

    python recolor.py            -> figure/whale/schemes/yuyu-recolor/tex/
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
SRC = WHALE / "tex"
DST = WHALE / "schemes" / "yuyu" / "tex"

# 只动头发那一摞，脸、身体、衣服、鲸鱼皮都不碰
HAIR = {
    "hair_back", "hair_back_curl", "hair_front_left", "hair_front_right",
    "sidelocks", "bangs", "ahoge",
    "crew_hair_back", "crew_ponytail", "crew_sidelocks",   # 店员装那条马尾
}

# 这些层是我自己画的（face.py），重上色时不要拿原版覆盖
KEEP = {"face"}

DARK = (52, 86, 148)
MID = (94, 148, 216)
LIGHT = (176, 214, 246)
LINE = (30, 40, 66)

LO = 0.30   # 低于这个亮度当成描边


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def ramp(t: float):
    return lerp(DARK, LIGHT, t) if t >= 0 else DARK


def shade(rgb):
    v = max(rgb) / 255.0
    if v < LO:
        return lerp(LINE, DARK, v / LO)
    t = (v - LO) / (1.0 - LO)
    # 中间那档让它更饱满一点
    if t < 0.5:
        return lerp(DARK, MID, t / 0.5)
    return lerp(MID, LIGHT, (t - 0.5) / 0.5)


def recolor(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            px[x, y] = (*shade((r, g, b)), a)
    return im


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(SRC.glob("*.png")):
        out = DST / src.name
        if src.stem in KEEP and out.exists():   # 我自己画的层，不许被原版盖掉
            continue
        if src.stem in HAIR:
            recolor(Image.open(src)).save(out)
            n += 1
        else:
            shutil.copy2(src, out)
    # 表情跟着复制，将来当整套 scheme 用
    feat = WHALE / "feat"
    if feat.is_dir():
        shutil.copytree(feat, DST.parent / "feat", dirs_exist_ok=True)
    print(f"recolored {n} hair layers -> {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
