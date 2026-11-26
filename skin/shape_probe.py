"""量一下原版脸的轮廓：每个高度上左右边在哪，好照着改我的脸型。

    python shape_probe.py   ->  _coop/shape_probe.log
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"


def profile(path: Path) -> None:
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    w, h = im.size
    x0, y0, x1, y1 = a.point(lambda v: 255 if v > 10 else 0).getbbox()
    bw, bh = x1 - x0, y1 - y0
    print(f"{path.name} size={w}x{h} box={x0},{y0},{x1},{y1} (w{bw} h{bh})")
    px = a.load()
    for i in range(0, 11):
        fy = i / 10
        y = int(y0 + fy * (bh - 1))
        row = [x for x in range(x0, x1) if px[x, y] > 10]
        if not row:
            print(f"  y={fy:.2f}  -")
            continue
        l, r = min(row), max(row)
        print(f"  y={fy:.2f}  l={(l - x0) / bw:.3f} r={(r - x0) / bw:.3f} w={(r - l) / bw:.3f}")


profile(WHALE / "tex" / "face.png")
profile(WHALE / "schemes" / "yuyu" / "tex" / "face.png")
