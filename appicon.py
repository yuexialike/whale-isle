"""程序图标：用哪张图，只在这个文件里决定一次。

月下 11-04 20:16：「把金鱼的这个标改成我们现在用的这个图标，然后底下这个图标也改成
我们现在用的这个图标。」

他说的「金鱼」是 `yuyu.ico`——最早那条白鱼，缩到 26 像素像条金鱼。
「现在用的」是桌面上那两个快捷方式认的那张：`品牌/icon/isla.ico`
（深藏青底、一条白鲸、底下一道细光）。两个地方都换成它：

  · 设置页左上角那个小方块（`settings_page._page_*` 里的 mark）；
  · 任务栏 / 窗口图标（`main.py` 里 `app.setWindowIcon`，还有各窗口自己带的那份）。

`isla.ico` 找不到就退回 `yuyu.ico`——老包里只有旧名字，不至于没图标。
打包时 `build.bat` 要把 `isla.ico`（和 `isla.png`）拷到 exe 旁边。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

NAMES = ("isla.ico", "yuyu.ico")          # 先找哪个，后找哪个


def here() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def path() -> Path | None:
    """现有能用的那个图标文件的路径。"""
    for name in NAMES:
        p = here() / name
        if p.exists():
            return p
    return None


def icon() -> QIcon:
    p = path()
    return QIcon(str(p)) if p else QIcon()


def pixmap(size: int) -> QPixmap | None:
    """给界面里的小方块用（设置页左上角那个）。没有就返回 None，调用方自己兜。"""
    p = here() / "isla.png"
    pm = QPixmap(str(p)) if p.exists() else None
    if pm is None or pm.isNull():
        ico = path()
        pm = QPixmap(str(ico)) if ico else None
    if pm is None or pm.isNull():
        return None
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
