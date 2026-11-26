"""把 drag_mouth / dizzy_mouth 退回原样（新框比原图还窄，贴的时候被切掉了一块）。

原图在部署副本 _coop/whale/feat/ 里还是干净的那份，直接拿回来；
model.json 里这两条的框也退回原值，之后再按正确的新框跑 mouth_boxes.py。

    python restore_mouths.py
"""
from __future__ import annotations

import re
from pathlib import Path
from shutil import copyfile

from PIL import Image

HERE = Path(__file__).resolve().parent
WHALE = HERE.parent / "figure" / "whale"
ORIG = WHALE / "feat"
BACKUP = HERE.parent.parent / "ref" / "cortico-world-desktop-pet" / "web" / "whale" / "feat"
MODEL = WHALE / "model.json"

OLD = {"drag_mouth": [709, 745, 766, 764], "dizzy_mouth": [711, 761, 782, 779]}
WANT = {"drag_mouth": (57, 19), "dizzy_mouth": (71, 18)}


def main() -> int:
    text = MODEL.read_text(encoding="utf-8")
    for name, box in OLD.items():
        src = BACKUP / f"{name}.png"
        if src.exists() and Image.open(src).size == WANT[name]:
            copyfile(src, ORIG / f"{name}.png")
            print(name, "还原自", src, Image.open(ORIG / f"{name}.png").size)
        else:
            print(name, "备份不可用", src)
        pat = re.compile(r'("%s"\s*:\s*\[)([^\]]*)(\])' % re.escape(name))
        body = "\n" + ",\n".join("    %d" % v for v in box) + "\n   "
        text, n = pat.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
        if n != 1:
            raise SystemExit(f"model.json 里没找到 {name}")
    MODEL.write_text(text, encoding="utf-8")
    print("写回", MODEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
