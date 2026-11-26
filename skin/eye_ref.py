"""把原版眼睛的四层（ball/iris/hl/lash）按 figure.js 的算法拼回原样，好看清楚我该画成什么样。

figure.js 里的叠法（master 像素，1:1）：
    ball  -> 画在 rect 原点
    iris  -> source-atop，画在 iris 矩形原点 + 眼睛偏移
    hl    -> 居中画在 hl 矩形中心
    lash  -> 绕 e.cx/e.cy 转 + 压扁后画，静止时就是原坐标

    python eye_ref.py   ->  blobs/eye-src.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
FEAT = WHALE / "schemes" / "yuyu" / "feat"
OUT = HERE.parent.parent / "blobs" / "eye-src.png"

S = 4  # 放大倍数，原版眼睛很小


def build(k: str, e: dict) -> Image.Image:
    ball = Image.open(FEAT / f"{k}_ball.png").convert("RGBA")
    iris = Image.open(FEAT / f"{k}_iris.png").convert("RGBA")
    hl = Image.open(FEAT / f"{k}_hl.png").convert("RGBA")
    lash = Image.open(FEAT / f"{k}_lash.png").convert("RGBA")

    bx, by = e["ball"][0], e["ball"][1]
    # 每层相对 ball 原点的位置
    off = {
        "ball": (0, 0),
        "iris": (e["iris"][0] - bx, e["iris"][1] - by),
        "hl": ((e["hl"][0] + e["hl"][2] - 2 * bx - hl.width) // 2,
               (e["hl"][1] + e["hl"][3] - 2 * by - hl.height) // 2),
        "lash": (e["lash"][0] - bx, e["lash"][1] - by),
    }
    xs = [off[n][0] for n in off] + [off[n][0] + im.width for n, im in
                                     (("ball", ball), ("iris", iris), ("hl", hl), ("lash", lash))]
    ys = [off[n][1] for n in off] + [off[n][1] + im.height for n, im in
                                     (("ball", ball), ("iris", iris), ("hl", hl), ("lash", lash))]
    x0, y0 = min(xs), min(ys)
    cv = Image.new("RGBA", (max(xs) - x0, max(ys) - y0), (0, 0, 0, 0))
    for im, n in ((ball, "ball"), (iris, "iris"), (hl, "hl"), (lash, "lash")):
        cv.alpha_composite(im, (off[n][0] - x0, off[n][1] - y0))
    return cv


def main() -> int:
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    eyes = model["feat"]["eyes"]

    rows = []
    for k in ("eyeL", "eyeR"):
        e = eyes[k]
        flat = Image.new("RGBA", (e["ball"][2] - e["ball"][0] + 40,
                                  e["ball"][3] - e["ball"][1] + 40), (0, 0, 0, 0))
        flat.alpha_composite(Image.open(FEAT / f"{k}_ball.png").convert("RGBA"), (20, 20))
        iris = Image.open(FEAT / f"{k}_iris.png").convert("RGBA")
        flat.alpha_composite(iris, (20 + e["iris"][0] - e["ball"][0], 20 + e["iris"][1] - e["ball"][1]))
        rows.append((k, build(k, e), [Image.open(FEAT / f"{k}_{n}.png").convert("RGBA")
                                      for n in ("ball", "iris", "hl", "lash")]))

    cells = []
    for k, whole, parts in rows:
        cells.append(whole)
        cells.extend(parts)
    width = sum(c.width for c in cells) + 24 * (len(cells) - 1)
    height = max(c.height for c in cells)
    sheet = Image.new("RGBA", (width, height), (26, 30, 44, 255))
    x = 0
    for c in cells:
        sheet.alpha_composite(c, (x, 0))
        x += c.width + 24

    # 再放大一份，方便看
    big = Image.new("RGBA", (width * 3, height * 3), (26, 30, 44, 255))
    big.alpha_composite(sheet.resize((width * 3, height * 3), Image.LANCZOS))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    big.save(OUT)
    print("src sheet", OUT, big.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
