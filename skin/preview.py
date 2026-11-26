"""把脸/刘海/呆毛按 model.json 的 box 拼成一张，两套皮肤并排放，好对比。

    python preview.py                     ->  base  |  yuyu
    python preview.py base yuyu-recolor   ->  base  |  yuyu-recolor
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
OUT = HERE.parent.parent / "blobs" / "skin-compare.png"

S = 3.0          # 1 logo 单位画几像素
UNIT = 256       # 小人所在的 256 单位方格
LAYERS = ["face", "bangs", "ahoge"]


def tex_dir(name: str) -> Path:
    return WHALE / "tex" if name in ("", "base", "deepseek") else WHALE / "schemes" / name / "tex"


def boxes() -> dict[str, list[float]]:
    model = json.loads((WHALE / "model.json").read_text(encoding="utf-8"))
    out = {}
    for p in model["parts"]:
        if p["id"] in LAYERS:
            out[p["id"]] = p["box"]
    return out


def draw(folder: Path, box) -> Image.Image:
    canvas = Image.new("RGBA", (int(UNIT * S), int(UNIT * S)), (0, 0, 0, 0))
    for name in LAYERS:                      # 已经按 z 排好：脸 8 < 刘海 13 < 呆毛 14
        tex = folder / f"{name}.png"
        if not tex.exists():
            continue
        x, y, w, h = box[name]
        im = Image.open(tex).convert("RGBA")
        im = im.resize((max(1, int(w * S)), max(1, int(h * S))), Image.LANCZOS)
        canvas.alpha_composite(im, (int(x * S), int(y * S)))
    return canvas


def main() -> int:
    left = sys.argv[1] if len(sys.argv) > 1 else "base"
    right = sys.argv[2] if len(sys.argv) > 2 else "yuyu"
    box = boxes()
    a = draw(tex_dir(left), box)
    b = draw(tex_dir(right), box)
    sheet = Image.new("RGBA", (a.width * 2 + 24, a.height), (24, 28, 40, 255))
    sheet.alpha_composite(a, (0, 0))
    sheet.alpha_composite(b, (a.width + 24, 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
