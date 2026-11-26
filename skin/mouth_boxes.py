"""把嘴的 sprite 框放大，并把原版那几张图平移着塞进新框里（原样不动，只是画布变大）。

为什么要动框：原版 neutral_mouth 只有 15x11 master 像素，脸上缩到屏幕也就十来个像素，
看上去就是「没有嘴」。框是全局的（配色方案共用），所以原版那几张得跟着挪，
不然原版配色里的嘴会整体偏移。挪的方式：把旧图贴在「它原来在屏幕上的位置」，
然后把 figure.js 里的 MOUTH_DY 清零——效果和以前一模一样。

    python mouth_boxes.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
ORIG = WHALE / "feat"
MODEL = WHALE / "model.json"

# 名字 -> (宽, 高, 嘴线中心的 master x, y)
NEW = {
    "neutral_mouth": (44, 26, 765.5, 769.5),
    "happy_mouth": (64, 50, 743.5, 770.5),
    "sleep_mouth": (36, 20, 751.0, 769.0),
    "drag_mouth": (64, 40, 737.5, 770.5),
    "love_mouth": (68, 50, 754.0, 770.0),
    "dizzy_mouth": (74, 30, 746.5, 770.0),
    "surprised_mouth": (44, 52, 771.0, 771.0),
}
# figure.js 原来那几个补偿（原版图比嘴线高）
DY = {"happy_mouth": 9, "drag_mouth": 16, "sleep_mouth": 4}


def main() -> int:
    text = MODEL.read_text(encoding="utf-8")
    sprites = json.loads(text)["feat"]["sprites"]

    for name, (w, h, cx, cy) in NEW.items():
        old = sprites[name]
        x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
        new = [x0, y0, x0 + w, y0 + h]
        if old == new:
            print(f"{name:16s} 已经是新框 {new}")
        else:
            src = ORIG / f"{name}.png"
            im = Image.open(src).convert("RGBA")
            dy = DY.get(name, 0)
            if im.size == (w, h):
                print(f"{name:16s} 图已经是新的，只补框")
            else:
                cv = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                cv.alpha_composite(im, (old[0] - x0, old[1] + dy - y0))
                cv.save(src)
                print(f"{name:16s} {im.size} -> {(w, h)} 原图贴在 ({old[0] - x0}, {old[1] + dy - y0})")
            # 只替换 sprites 里这一条（"名字": [ ... ] 的第一次出现）
            pat = re.compile(r'("%s"\s*:\s*\[)([^\]]*)(\])' % re.escape(name))
            body = "\n" + ",\n".join("    %d" % v for v in new) + "\n   "
            text, n = pat.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
            if n != 1:
                raise SystemExit(f"model.json 里没找到 {name} 的框")
            sprites[name] = new

    MODEL.write_text(text, encoding="utf-8")
    print("写回", MODEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
