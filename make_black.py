"""做一张纯黑的首帧图 / 一张纯黑的尾帧。

minimax H3 max 只吃「首帧 + 尾帧」两张图（00:16 月下发现的），所以这两张得单独备着：
  00-black.png    纯黑 2560×1600 —— 当首帧
  02-lines.pn g   线条人形那张 —— 当尾帧（他生成）

用法：双击 run-black.bat，结果写到 data\\boot\\00-black.png
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "boot" / "00-black.png"

W, H = 2560, 1600
Image.new("RGB", (W, H), (0, 0, 0)).save(OUT)
print(f"写了 {OUT}  {W}x{H}")
