"""给新家画一个图标。

月下 13:52 说：「你这个软件在桌面上要有一个小图标的，你要不要给自己设计一个
非常非常帅气的小图标？」——要。所以自己画，不找图：深蓝紫渐变的小方砖，
里面一条白鲸，再飘一颗气泡。

为什么自己画而不是用画图模型：图标要缩到 16/32 像素还认得出，得是干净的矢量
硬边。（顺带一句：那会儿 ComfyUI 也没开。）所以全部用 QPainter 画，再自己拼
一个多尺寸的 .ico——Qt 的 ico 插件一次只写一张，多尺寸得手工拼。

两个候选造型一起出图，挑一个：
    python make_icon.py            # 出 yuyu.png / yuyu.ico（默认造型）+ compare.png
"""

from __future__ import annotations

import struct
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)

HERE = Path(__file__).resolve().parent

TOP = QColor("#6C8BFF")        # 左上亮一点的蓝紫
BOTTOM = QColor("#141C3F")     # 右下压深的夜蓝

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
DEFAULT = "whale"              # tail / whale


# ---------------------------------------------------------------- 造型

def _tail_path() -> QPainterPath:
    """造型 A：一条鲸尾（细茎 + 两片往上甩的尾鳍 + 中间朝下的缺口）。"""
    p = QPainterPath()
    p.moveTo(128, 206)
    p.cubicTo(124, 206, 121, 202, 121, 196)
    p.lineTo(121, 156)
    p.cubicTo(96, 158, 62, 140, 46, 108)
    p.cubicTo(40, 94, 44, 74, 56, 62)
    p.cubicTo(70, 50, 96, 70, 108, 94)
    p.cubicTo(114, 108, 120, 124, 128, 134)
    p.cubicTo(136, 124, 142, 108, 148, 94)
    p.cubicTo(160, 70, 186, 50, 200, 62)
    p.cubicTo(212, 74, 216, 94, 210, 108)
    p.cubicTo(194, 140, 160, 158, 135, 156)
    p.lineTo(135, 196)
    p.cubicTo(135, 202, 132, 206, 128, 206)
    p.closeSubpath()
    return p


def _whale_body() -> QPainterPath:
    """造型 B：侧身朝左的白鲸身子（圆钝的脑袋、胖肚子）。"""
    p = QPainterPath()
    p.moveTo(62, 160)
    p.cubicTo(50, 152, 48, 138, 54, 124)       # 前端：圆钝的额头
    p.cubicTo(62, 106, 92, 94, 126, 96)        # 背脊拱起来
    p.cubicTo(150, 97, 164, 110, 172, 124)     # 收到尾巴根
    p.cubicTo(176, 132, 174, 138, 168, 142)    # 尾巴根下沿
    p.cubicTo(152, 162, 110, 172, 84, 168)     # 肚子
    p.cubicTo(74, 166, 66, 163, 62, 160)       # 回到下巴
    p.closeSubpath()
    return p


def _whale_fluke() -> QPainterPath:
    """造型 B 的尾鳍：侧看是两片朝右张开、有点厚度的尖叶。

    一定得是**一条**连起来的路径。第一版把两片叶各写成一个 closeSubpath，
    两条闭合边在尾巴根交叉，中间就露出一颗蓝色的菱形洞——14:00 在 compare.png
    里看得清清楚楚。现在从尾根出去绕一圈再回到尾根，缺口开在右边。
    """
    p = QPainterPath()
    p.moveTo(150, 118)                          # 塞进身体里，尾巴根不留缝
    p.cubicTo(190, 106, 212, 96, 222, 86)       # 上叶外缘
    p.cubicTo(229, 80, 235, 88, 229, 97)        # 上叶尖
    p.cubicTo(218, 112, 202, 126, 190, 130)     # 收进中间那个缺口
    p.cubicTo(202, 134, 218, 148, 229, 159)     # 下叶尖
    p.cubicTo(235, 168, 229, 176, 222, 170)
    p.cubicTo(212, 160, 190, 150, 150, 140)     # 下叶外缘回到尾根
    p.closeSubpath()
    return p


def _spout(p: QPainter) -> None:
    """头顶那股水花：三个小圆点往上飘。缩到 16px 会糊掉，所以太小时不画。"""
    for cx, cy, r in ((112, 74, 5.0), (104, 56, 4.0), (94, 40, 3.0)):
        p.drawEllipse(QPointF(cx, cy), r, r)


def _draw_mark(p: QPainter, variant: str, size: int) -> None:
    """在 256 的画布上画白色的那个记号。"""
    p.setBrush(QColor("#FFFFFF"))
    if variant == "whale":
        if size >= 32:
            _spout(p)
        p.drawPath(_whale_body())
        p.drawPath(_whale_fluke())
        if size >= 24:
            # 眼睛：把方砖的深蓝透出来
            p.setBrush(QColor(36, 54, 132, 235))
            p.drawEllipse(QPointF(84, 130), 4.6, 4.6)
    else:
        p.drawPath(_tail_path())

    # 气泡：只有「鲸尾」那版用。鲸鱼那版头顶已经有水花，再放一颗圆点两边抢，
    # 缩到 32px 就糊成一团——留着水花更干净。
    if variant == "tail":
        p.setBrush(QColor(255, 255, 255, 236))
        p.drawEllipse(QPointF(128, 36), 14, 14)


# ---------------------------------------------------------------- 出图

def render(size: int, variant: str = DEFAULT) -> QImage:
    """画一张 size×size 的图标（透明底、圆角方砖）。"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(size / 256.0, size / 256.0)      # 统一按 256 的画布来

    # 圆角方砖 + 斜向渐变
    badge = QRectF(10, 10, 236, 236)
    grad = QLinearGradient(QPointF(28, 22), QPointF(228, 240))
    grad.setColorAt(0.0, TOP)
    grad.setColorAt(0.55, QColor("#3450C8"))
    grad.setColorAt(1.0, BOTTOM)
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(badge, 56, 56)

    # 左上角压一层很淡的高光，缩到小尺寸也有一点立体感
    halo = QRadialGradient(QPointF(70, 56), 170)
    halo.setColorAt(0.0, QColor(255, 255, 255, 46))
    halo.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(halo)
    p.drawRoundedRect(badge, 56, 56)

    _draw_mark(p, variant, size)

    # 极细一圈内描边，贴着浅色桌面时轮廓不糊
    pen = QPen(QColor(255, 255, 255, 38))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(badge.adjusted(1, 1, -1, -1), 55, 55)

    p.end()
    return img


def compare_sheet(path: Path) -> None:
    """三个造型并排看：256 的大图 + 32/16 的小图，挑的时候一眼见分晓。"""
    w, h = 900, 340
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor("#f2f4f8"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    for i, variant in enumerate(("whale", "tail")):
        x = 30 + i * 440
        p.drawImage(x, 40, render(256, variant))
        for j, s in enumerate((32, 24, 16)):
            p.drawImage(x + 280 + j * 44, 60, render(s, variant))
        p.setPen(QColor("#333"))
        f = p.font()
        f.setPointSizeF(11)
        p.setFont(f)
        p.drawText(x, 320, variant)
    p.end()
    img.save(str(path), "PNG")


def _png_bytes(img: QImage) -> bytes:
    """存成 PNG 字节。绕一圈走临时文件——直接往 QBuffer 里 save 在不同 PySide
    版本上时灵时不灵，落盘最稳。"""
    tmp = Path(tempfile.gettempdir()) / "homestead-icon-tmp.png"
    if not img.save(str(tmp), "PNG"):
        raise RuntimeError("QImage.save(PNG) 返回 False")
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def write_ico(path: Path, sizes: list[int], variant: str = DEFAULT) -> None:
    """自己拼 .ico：一个头 + 每张一个目录项 + 各张 PNG 数据。

    Windows 从 Vista 起认 PNG 压缩的 ico，比 BMP 小得多，也省得自己算调色板。
    """
    images = [_png_bytes(render(s, variant)) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))     # reserved, type=icon, count
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s, data in zip(sizes, images):
        side = 0 if s >= 256 else s                  # 256 在目录里写 0
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(head + entries + blobs)


def main() -> int:
    try:
        app = QGuiApplication(sys.argv)               # QPainter 要一个 application

        png = HERE / "yuyu.png"
        if not render(512).save(str(png), "PNG"):
            raise RuntimeError(f"写不出 {png}")
        ico = HERE / "yuyu.ico"
        write_ico(ico, SIZES)
        compare_sheet(HERE / "compare.png")

        print(f"png  {png}  {png.stat().st_size} bytes")
        print(f"ico  {ico}  {ico.stat().st_size} bytes  ({len(SIZES)} sizes)")
        print(f"cmp  {HERE / 'compare.png'}")
        app.quit()
        return 0
    except Exception:                                 # noqa: BLE001
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
