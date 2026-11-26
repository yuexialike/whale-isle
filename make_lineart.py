"""把水里的正脸照做成「流光线条」——开场第一帧用。

月下 23:27：「第一帧就换成那个在水里的正脸照，把它做一个线条化的处理……
慢慢出现线条，慢慢出现人像再往上游」「线条走流光线条」。
23:30 又点：「线条太密了，就用很简单几个线把轮廓大概描出来，主要外轮廓，不用画阴影」。

做法（23:34 定下来）：
1. **外轮廓**：把人物从深蓝水里切出来（低阈值 + 中值去噪），吃掉一圈相减，得到一条闭合的轮廓线；
2. **内部几笔**：用「局部对比度归一化」的 DoG，只有比周围明显亮/暗的地方才留（眼窝、下巴、发分区），
   这样不会再出现满屏的碎线；
3. 线染冷白偏青，垫一层大半径光晕，烤进 02-lines.png（带 alpha）。

用法：python make_lineart.py [源文件名]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
BOOT = HERE / "data" / "boot"
OUT = BOOT / "02-lines.png"
BIG = 2048


def soft_knee(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((x - lo) / (hi - lo + 1e-6), 0.0, 1.0)


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "06-front.png.png"
    src = BOOT / name
    if not src.exists():
        raise SystemExit(f"找不到 {src}")
    print(f"源图：{src.name}")

    im = Image.open(src).convert("RGB")
    print(f"  原尺寸 {im.width}x{im.height}")
    if max(im.size) < BIG:
        im = im.resize((BIG, BIG), Image.LANCZOS)
    w, h = im.size
    gray = im.convert("L")

    arr = np.asarray(gray, dtype=np.float32)

    # ---- 1) 切出人物 ----
    t = float(np.percentile(arr, 45))
    print(f"  取 45 分位当切分阈值 = {t:.0f}")
    mask = Image.fromarray(((arr > t) * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MedianFilter(7))

    # ---- 2) 把这块「抹平」：糊开再切一刀，边界就成了一条顺滑的线，碎块全没了 ----
    smooth = mask.filter(ImageFilter.GaussianBlur(11))
    blob = Image.fromarray(((np.asarray(smooth, dtype=np.float32) > 110) * 255).astype(np.uint8))
    blob = blob.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    inner = blob.filter(ImageFilter.MinFilter(17))
    outline = np.asarray(ImageChops.subtract(blob, inner), dtype=np.float32) / 255.0
    inner_line = outline * 0.0

    a = np.clip(outline, 0.0, 1.0)
    aimg = Image.fromarray((a * 255).astype(np.uint8))
    aimg = aimg.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.4))
    a = np.asarray(aimg, dtype=np.float32) / 255.0

    rgb = np.zeros((h, w, 3), dtype=np.float32)
    rgb[:, :, 0] = 178        # 冷白，带一点青
    rgb[:, :, 1] = 232
    rgb[:, :, 2] = 250
    line = Image.fromarray(np.dstack([rgb, (a * 255)]).astype(np.uint8), "RGBA")

    glow = line.filter(ImageFilter.GaussianBlur(16.0))
    ga = np.asarray(glow.split()[3], dtype=np.float32) * 0.75
    glow = Image.fromarray(np.dstack([np.asarray(glow)[:, :, :3],
                                      ga.astype(np.uint8)]).astype(np.uint8), "RGBA")

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(line)
    out.save(OUT)

    print(f"写好 {OUT.name}：{w}x{h}，外轮廓 {((outline > 0.5).mean() * 100):.2f}%  "
          f"内部线 {(inner_line > 0.5).mean() * 100:.2f}%  合计 {(a > 0.25).mean() * 100:.1f}%")


if __name__ == "__main__":
    sys.exit(main())
