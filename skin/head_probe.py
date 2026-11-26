"""把「脸皮 + 眼睛 + 嘴」按 master 坐标拼成整张脸，好判断腮红和嘴的位置对不对。

屏幕上那个预览太小，靠截图看不清；这里按 master 像素 1:1 拼、再放大 3 倍。
左边：平常的脸（neutral 嘴）；右边：说话/笑（happy 嘴）。

拼法（和 figure.js 对齐）：
    脸皮 face.png 铺在 plate 的 master 矩形里（缩放来自 model 的 box）
    每只眼睛：ball 原尺寸放在 ball 框原点，iris 放在 iris 框原点，hl 居中在 hl 框中心，
              lash 放在 lash 框原点（静止状态就是原坐标）
    嘴：sprite 框原点 + MOUTH_DY（现在是空的）
这些只是静止状态，动态的眼皮/转动不算——判断位置够用。

    python head_probe.py   ->  blobs/head-probe.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
SCHEME = WHALE / "schemes" / "yuyu"
OUT = HERE.parent.parent / "blobs" / "head-probe.png"

S = 0.19
X0, FEET = 650, 1363
K = 3            # 输出再放大
MOUTH_DY = {}    # 和 figure.js 保持一致
PANELS = ["neutral_mouth", "happy_mouth"]


def master_rect(box):
    x, y, w, h = box
    mx = X0 + (x - 128) / S
    my = FEET - (256 - y) / S
    return mx, my, w / S, h / S


def build(model, mouth):
    sprites = model["feat"]["sprites"]
    eyes = model["feat"]["eyes"]
    plate = next(p for p in model["parts"] if p["id"] == "face")
    px, py, pw, ph = master_rect(plate["box"])
    cw, ch = int(round(pw)), int(round(ph))
    head = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    skin = Image.open(SCHEME / "tex" / "face.png").convert("RGBA")
    head.alpha_composite(skin.resize((cw, ch), Image.LANCZOS), (0, 0))

    def put(im, x, y):
        head.alpha_composite(im, (int(round(x - px)), int(round(y - py))))

    for k in ("eyeL", "eyeR"):
        e = eyes[k]
        put(Image.open(SCHEME / "feat" / f"{k}_ball.png").convert("RGBA"), e["ball"][0], e["ball"][1])
        put(Image.open(SCHEME / "feat" / f"{k}_iris.png").convert("RGBA"), e["iris"][0], e["iris"][1])
        hl = Image.open(SCHEME / "feat" / f"{k}_hl.png").convert("RGBA")
        put(hl, (e["hl"][0] + e["hl"][2] - hl.width) / 2, (e["hl"][1] + e["hl"][3] - hl.height) / 2)
        put(Image.open(SCHEME / "feat" / f"{k}_lash.png").convert("RGBA"), e["lash"][0], e["lash"][1])

    b = sprites[mouth]
    im = Image.open(SCHEME / "feat" / f"{mouth}.png").convert("RGBA")
    put(im, b[0], b[1] + MOUTH_DY.get(mouth, 0))
    return head, (px, py), sprites


def main() -> int:
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    panels = []
    for name in PANELS:
        head, off, _ = build(model, name)
        panels.append(head.resize((head.width * K, head.height * K), Image.LANCZOS))

    w = sum(p.width for p in panels) + 40 * (len(panels) - 1)
    h = max(p.height for p in panels)
    sheet = Image.new("RGBA", (w, h), (26, 30, 44, 255))
    x = 0
    for p in panels:
        sheet.alpha_composite(p, (x, 0))
        x += p.width + 40

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print("head", sheet.size, "panels", PANELS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
