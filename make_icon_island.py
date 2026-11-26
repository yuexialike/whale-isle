"""给「鲸屿」画一个正式版图标——不是我的脸，是这只软件的招牌。

月下 14:26 说：自己用现在那张（我的脸）可以，但还得设计一个高端大气上档次的图标，
这样别人用的时候也有个像样的快捷方式。所以：

    深海军蓝小方砖 + 一道细细的月光 + 一头发着冷光的白鲸。

配色走金 + 藏青（金月亮、白鲸身、深蓝底），缩到 16 像素还是一个形状，
不像渐变色块那样一糊就散。全部 QPainter 手画，多尺寸 .ico 自己拼。

    python make_icon_island.py     # 出 whale-isle.png / whale-isle.ico / icon-compare.png
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

TOP = QColor("#1A2E58")        # 左上偏亮的藏青
MID = QColor("#101B36")
BOTTOM = QColor("#070C18")     # 右下压到近乎黑
GOLD = QColor("#F3C97C")       # 月亮
GLOW = QColor("#6FA8FF")       # 鲸身外那圈冷光

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


# ---------------------------------------------------------------- 造型

def _whale_body() -> QPainterPath:
    """侧身朝左的白鲸身子（跟 make_icon.py 里那一版一致，圆额头胖肚子）。"""
    p = QPainterPath()
    p.moveTo(62, 160)
    p.cubicTo(50, 152, 48, 138, 54, 124)
    p.cubicTo(62, 106, 92, 94, 126, 96)
    p.cubicTo(150, 97, 164, 110, 172, 124)
    p.cubicTo(176, 132, 174, 138, 168, 142)
    p.cubicTo(152, 162, 110, 172, 84, 168)
    p.cubicTo(74, 166, 66, 163, 62, 160)
    p.closeSubpath()
    return p


def _whale_fluke() -> QPainterPath:
    """尾鳍：一片连起来的两叶，缺口开在右边。"""
    p = QPainterPath()
    p.moveTo(150, 118)
    p.cubicTo(190, 106, 212, 96, 222, 86)
    p.cubicTo(229, 80, 235, 88, 229, 97)
    p.cubicTo(218, 112, 202, 126, 190, 130)
    p.cubicTo(202, 134, 218, 148, 229, 159)
    p.cubicTo(235, 168, 229, 176, 222, 170)
    p.cubicTo(212, 160, 190, 150, 150, 140)
    p.closeSubpath()
    return p


def _whale() -> QPainterPath:
    """身子 + 尾巴合成一条路径，描边和填充都一次走完，接缝不会露出来。"""
    p = _whale_body()
    p.addPath(_whale_fluke())
    return p.simplified()


def _moon() -> QPainterPath:
    """左上角那弯月亮：大圆挖掉一个偏右上的小圆。"""
    p = QPainterPath()
    p.addEllipse(QPointF(74, 62), 27, 27)
    cut = QPainterPath()
    cut.addEllipse(QPointF(85, 51), 24, 24)
    return p.subtracted(cut)


# ---------------------------------------------------------------- 出图

def render(size: int) -> QImage:
    """画一张 size×size 的图标（透明底、圆角方砖）。"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(size / 256.0, size / 256.0)

    badge = QRectF(8, 8, 240, 240)

    # 底：斜向三段藏青
    grad = QLinearGradient(QPointF(30, 20), QPointF(226, 240))
    grad.setColorAt(0.0, TOP)
    grad.setColorAt(0.52, MID)
    grad.setColorAt(1.0, BOTTOM)
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(badge, 62, 62)

    # 左上角一点冷光，让方砖不那么平
    halo = QRadialGradient(QPointF(64, 48), 190)
    halo.setColorAt(0.0, QColor(110, 160, 255, 58))
    halo.setColorAt(1.0, QColor(110, 160, 255, 0))
    p.setBrush(halo)
    p.drawRoundedRect(badge, 62, 62)

    # 月亮：太小的时候省掉，两边抢会糊
    if size >= 24:
        p.setBrush(GOLD)
        p.setPen(Qt.NoPen)
        p.drawPath(_moon())

    # 鲸：先描几圈低透明度的冷光，再填白
    whale = _whale()
    if size >= 32:
        for width, alpha in ((18.0, 18), (11.0, 26), (6.0, 38)):
            pen = QPen(QColor(GLOW.red(), GLOW.green(), GLOW.blue(), alpha))
            pen.setWidthF(width)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(whale)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(whale)

    # 眼睛：把深蓝透出来
    if size >= 32:
        p.setBrush(QColor(12, 20, 40, 235))
        p.drawEllipse(QPointF(84, 130), 4.8, 4.8)

    # 极细一圈内描边，贴着浅色桌面时轮廓不糊
    pen = QPen(QColor(255, 255, 255, 30))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(badge.adjusted(1, 1, -1, -1), 61, 61)

    p.end()
    return img


def compare_sheet(path: Path) -> None:
    """256 的大图配 64/32/24/16 的小图，看它在任务栏里认不认得出。"""
    img = QImage(760, 340, QImage.Format_ARGB32)
    img.fill(QColor("#f2f4f8"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.drawImage(30, 42, render(256))
    for j, s in enumerate((64, 48, 32, 24, 16)):
        p.drawImage(320 + j * 80, 60, render(s))
    p.setPen(QColor("#333"))
    f = p.font()
    f.setPointSizeF(11)
    p.setFont(f)
    p.drawText(320, 320, "64 / 48 / 32 / 24 / 16")
    p.end()
    img.save(str(path), "PNG")


def _png_bytes(img: QImage) -> bytes:
    """存成 PNG 字节（绕一圈临时文件，比 QBuffer 稳）。"""
    tmp = Path(tempfile.gettempdir()) / "island-icon-tmp.png"
    if not img.save(str(tmp), "PNG"):
        raise RuntimeError("QImage.save(PNG) 返回 False")
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def write_ico(path: Path, sizes: list[int]) -> None:
    """自己拼 .ico：一个头 + 每张一个目录项 + 各张 PNG 数据。"""
    images = [_png_bytes(render(s)) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s, data in zip(sizes, images):
        side = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(head + entries + blobs)


def main() -> int:
    try:
        app = QGuiApplication(sys.argv)

        png = HERE / "whale-isle.png"
        if not render(512).save(str(png), "PNG"):
            raise RuntimeError(f"写不出 {png}")
        ico = HERE / "whale-isle.ico"
        write_ico(ico, SIZES)
        compare_sheet(HERE / "icon-compare.png")

        print(f"png  {png}  {png.stat().st_size} bytes")
        print(f"ico  {ico}  {ico.stat().st_size} bytes  ({len(SIZES)} sizes)")
        app.quit()
        return 0
    except Exception:                                 # noqa: BLE001
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
