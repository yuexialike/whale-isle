"""把开场第一幕里那条鱼抠出来，做成「鲸屿」的图标。

月下 14:26/14:27 说的：远景深海那一幕里头那条鱼的样子特别好，抠下来、周围透明化当图标。

源图 `data/boot/02.png`（1280×720，我自己 10-31 用 MOSS 出的那一幕），鱼在正中间
大概 70×116 像素，很小。做法：

  1. 裁一块围着鱼的方窗；
  2. 用大半径高斯模糊估出「周围的水」当背景，原图减掉它 → 差值大的地方就是鱼
     （身子比水暗、轮廓比水亮，取绝对差正好两边都吃进来）；
  3. 差值归一化当 alpha，轻微羽化，颜色还是原图那点冷青；
  4. 放到一块深海水色的圆角砖上（纯透明底的话，鱼身是黑的，浅色桌面上就看不见了）。

出三样：
  fish-cut.png      只有鱼，四周全透明 —— 月下要的那张
  whale-isle.png    图标大图（512）
  whale-isle.ico    多尺寸图标（16…256）

    python make_icon_fish.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "boot" / "02.png"

# 鱼在源图上的位置（量出来的：x 616..686, y 228..344），四周留出足够的水
BOX = (556, 176, 744, 404)          # 188 × 228

UP = 8                              # 先把裁下来的那块放大八倍再干活
CANVAS = 1024                       # 图标母版尺寸
FISH_PX = 760                       # 鱼在母版里有多高
RADIUS = 232                        # 圆角砖的圆角（母版 1024）

TOP = (18, 34, 62)                  # 砖的上沿：深海藏青
BOTTOM = (5, 9, 18)                 # 砖的下沿：几乎全黑
GLOW = (60, 190, 220)               # 底部那层冷光

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


# ---------------------------------------------------------------- 抠鱼

def cut_fish() -> Image.Image:
    """返回只有鱼、四周透明的 RGBA 大图。"""
    crop = Image.open(SRC).convert("RGB").crop(BOX)
    water = crop.filter(ImageFilter.GaussianBlur(46))

    a = np.asarray(crop, dtype=np.float32)
    b = np.asarray(water, dtype=np.float32)
    diff = a - b

    # 身子偏暗、轮廓偏亮，取每个像素三通道里绝对值最大的那个当「离水多远」
    mag = np.abs(diff).max(axis=2)
    lo, hi = np.percentile(mag, 55), np.percentile(mag, 99.6)
    alpha = np.clip((mag - lo) / max(hi - lo, 1e-6), 0.0, 1.0) ** 0.75

    # 羽化一层，别让边缘是锯齿；同时把散落的雪花噪点压掉
    am = Image.fromarray((alpha * 255).astype(np.uint8), "L")
    am = am.filter(ImageFilter.GaussianBlur(2.2))
    am = am.point(lambda v: 0 if v < 26 else v)

    # 颜色：源图里鱼身几乎和水一样黑，直接搬过来缩到 32 像素就成一小片墨。
    # 所以整体抬亮一档、再补一点底光，让身子变成淡淡的蓝灰，轮廓还是那圈冷青。
    rgb = np.clip(a * 2.35 + 46, 0, 255).astype(np.uint8)
    fish = Image.fromarray(rgb, "RGB").convert("RGBA")
    fish.putalpha(am)

    # 放大八倍再来摆位置，缩放的时候不糊
    big = fish.resize((fish.width * UP, fish.height * UP), Image.LANCZOS)
    return big


def fish_box(img: Image.Image) -> tuple[int, int, int, int]:
    """这条鱼在放大图里占了多大一块（按 alpha 找边界）。"""
    box = img.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    if box is None:
        raise RuntimeError("没找到鱼——alpha 全空了")
    return box


# ---------------------------------------------------------------- 拼图标

def gradient_badge(size: int) -> Image.Image:
    """深海水色的圆角砖：竖着渐变 + 底部一层冷光 + 四边压暗。"""
    yy = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    top = np.array(TOP, dtype=np.float32)[None, None, :]
    bot = np.array(BOTTOM, dtype=np.float32)[None, None, :]
    grad = top + (bot - top) * (yy ** 1.15)
    bg = np.repeat(grad, size, axis=1)

    # 底部偏中的冷光（就是源图最下沿那条青光）
    cx, cy, rad = size * 0.5, size * 0.98, size * 0.62
    xs = np.arange(size, dtype=np.float32)[None, :]
    ys = np.arange(size, dtype=np.float32)[:, None]
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / rad
    halo = np.clip(1.0 - d, 0.0, 1.0)[..., None] ** 2.2
    bg = bg + halo * np.array(GLOW, dtype=np.float32) * 0.34

    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    # 圆角
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * RADIUS / CANVAS), fill=255)
    img.putalpha(mask)

    # 极细一圈内描边，贴浅色桌面时轮廓不糊
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        (1, 1, size - 2, size - 2), radius=int(size * RADIUS / CANVAS),
        outline=(255, 255, 255, 34), width=max(1, size // 256 + 1))
    return Image.alpha_composite(img, ring)


def compose(fish: Image.Image, size: int = CANVAS) -> Image.Image:
    """鱼摆到砖中间偏下一点点——留出头顶那片水，看着才像「深处」。"""
    badge = gradient_badge(size)
    f = fish.copy()
    box = fish_box(f)
    fw, fh = box[2] - box[0], box[3] - box[1]

    want = size * FISH_PX / CANVAS
    k = want / fh
    f = f.resize((max(1, int(f.width * k)), max(1, int(f.height * k))), Image.LANCZOS)

    box = fish_box(f)
    fx, fy = box[0] + (box[2] - box[0]) / 2, box[1] + (box[3] - box[1]) / 2
    px, py = size / 2, size * 0.545
    at = (int(px - fx), int(py - fy))

    # 先在鱼后面铺一层散开的冷光，深水里那点光晕就是这个味道
    halo = Image.new("RGBA", f.size, (90, 205, 235, 0))
    halo.putalpha(f.getchannel("A").filter(ImageFilter.GaussianBlur(26)).point(
        lambda v: int(v * 0.55)))
    badge.alpha_composite(halo, at)

    badge.alpha_composite(f, at)
    return badge


# ---------------------------------------------------------------- 存盘

def _png_bytes(img: Image.Image) -> bytes:
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def write_ico(path: Path, master: Image.Image, sizes: list[int]) -> None:
    """自己拼 .ico，每张都从母版单独缩，小尺寸单独锐化一下。"""
    images = []
    for s in sizes:
        im = master.resize((s, s), Image.LANCZOS)
        if s <= 32:                      # 小图标不锐化就糊成一团
            im = im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=0))
        images.append(_png_bytes(im))

    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s, data in zip(sizes, images):
        side = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(head + entries + blobs)


def main() -> int:
    if not SRC.exists():
        print(f"源图不在：{SRC}")
        return 1

    fish = cut_fish()
    box = fish_box(fish)

    fish.crop(box).save(str(HERE / "fish-cut.png"))          # 只要鱼，四周透明
    master = compose(fish)
    master.resize((512, 512), Image.LANCZOS).save(str(HERE / "whale-isle.png"))
    write_ico(HERE / "whale-isle.ico", master, SIZES)

    print("fish-cut.png   " + str((HERE / "fish-cut.png").stat().st_size) + " bytes")
    print("whale-isle.png " + str((HERE / "whale-isle.png").stat().st_size) + " bytes")
    print("whale-isle.ico " + str((HERE / "whale-isle.ico").stat().st_size)
          + f" bytes ({len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
