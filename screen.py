"""眼睛：看一眼屏幕。

只管「拿到图」这一件事，不管「准不准看」——那个由 gate 决定，工具层去问。

做法（从 Coop 的 `cua/*.ts` 学的是**小心**，不是代码）：
  1. 整块屏抓下来（Qt 的 grabWindow，不用额外库）
  2. 缩到不超过 1280×800（模型看得清就够了，再大是浪费）
  3. 存进 data/screen/，文件名带时间，回头能查
  4. 回来时顺带说清：鼠标在哪、前台窗口叫什么叫
  5. **不画鼠标指针**——Coop 会把指针画上去，这一版先不画，免得图里多一个假东西
"""
from __future__ import annotations

import ctypes
import datetime as _dt
from pathlib import Path

SHOT_MAX = (1280, 800)


def dpi_aware() -> None:
    """开进程就调，**要在 QApplication 之前**——之后再调，Qt 已经按逻辑像素算好了。

    不调的话：截图是「缩过的逻辑像素」（1707×1067），鼠标坐标也是逻辑的，
    跟外面看到的 2560×1600 差 0.75 倍，点起来会偏。
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _dpi_aware() -> None:
    """老名字，留着兼容；正经应该在 main 开头调 dpi_aware()。"""
    dpi_aware()


def foreground_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or "（无）"
    except Exception:
        return "（读不到）"


def cursor_pos() -> tuple[int, int]:
    try:
        from PySide6.QtGui import QCursor
        p = QCursor.pos()
        return int(p.x()), int(p.y())
    except Exception:
        return (-1, -1)


def display_size() -> tuple[int, int]:
    try:
        from PySide6.QtWidgets import QApplication
        scr = QApplication.primaryScreen()
        s = scr.size()
        return int(s.width()), int(s.height())
    except Exception:
        return (0, 0)


# 最近一张截图的比例：外面给我的坐标是「截图坐标」，点的时候要乘回物理像素。
LAST = {"scale": 1.0, "path": ""}


def to_physical(x: float, y: float) -> tuple[int, int]:
    """截图坐标 -> 屏幕实际像素。没截过图就原样当像素用。"""
    k = float(LAST.get("scale") or 1.0)
    return int(round(x * k)), int(round(y * k))


def grab(out_dir: Path) -> dict:
    """抓一张。回来的是 dict：path / size / screen / cursor / foreground。"""
    _dpi_aware()
    from PySide6.QtWidgets import QApplication

    # 别的脚本里（没有窗口的时候）也得能截：没 QApplication 就现造一个。
    app = QApplication.instance() or QApplication([])
    scr = app.primaryScreen()
    if scr is None:                     # 真没有屏幕（远程/无头）就明说，别编
        raise RuntimeError("拿不到屏幕（没有 primaryScreen）")
    dpr = float(scr.devicePixelRatio() or 1.0)
    # Qt 给的是**逻辑像素**（系统缩放 150% 时 2560 会报成 1707）。
    # 真正点鼠标要的是物理像素，所以都乘上 dpr 报出去——外面按这个算才不会偏。
    full_w = int(round(scr.size().width() * dpr))
    full_h = int(round(scr.size().height() * dpr))
    pix = scr.grabWindow(0)            # 0 = 整个屏幕

    # 缩到不超过 SHOT_MAX，只缩不放
    w, h = pix.width(), pix.height()
    k = min(SHOT_MAX[0] / w, SHOT_MAX[1] / h, 1.0)
    if k < 1.0:
        pix = pix.scaled(int(w * k), int(h * k))

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%H%M%S")
    path = out_dir / f"screen-{stamp}.png"
    if not pix.save(str(path), "PNG"):
        raise RuntimeError(f"存不下来：{path}")

    cx, cy = cursor_pos()
    shot = {
        "path": str(path),
        "shot": (pix.width(), pix.height()),
        "screen": (full_w, full_h),
        "scale": round(full_w / max(1, pix.width()), 3),
        "cursor": (int(round(cx * dpr)), int(round(cy * dpr))),
        "foreground": foreground_title(),
    }
    LAST["scale"] = shot["scale"]
    LAST["path"] = shot["path"]
    return shot


def describe(shot: dict) -> str:
    """把 grab() 的结果说成一句人话，给模型看。"""
    sw, sh = shot["screen"]
    pw, ph = shot["shot"]
    cx, cy = shot["cursor"]
    return (f"截图 {pw}×{ph}（屏幕 {sw}×{sh}）；鼠标在 ({cx}, {cy})；"
            f"**截图坐标 × {shot['scale']} = 屏幕实际像素**；"
            f"前台窗口「{shot['foreground']}」；存在 {shot['path']}")


def grab_region(out_dir: Path, x: int, y: int, w: int, h: int, zoom: float = 2.0) -> dict:
    """从屏幕**重新**截一小块，放大看清楚（截图缩过之后小字会糊）。

    传进来的 x/y/w/h 是**最近一张截图的坐标**（跟 beep 一样，点哪儿就传哪儿）；
    内部先乘回物理像素再裁，所以裁的是真屏幕上那一块，不是缩过的那张图。
    出来的图最多 1280×800；面积小就放大 `zoom` 倍，字才看得清。
    """
    _dpi_aware()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    scr = app.primaryScreen()
    if scr is None:
        raise RuntimeError("拿不到屏幕（没有 primaryScreen）")

    k = float(LAST.get("scale") or 1.0)          # 截图坐标 -> 物理像素
    px, py = int(round(x * k)), int(round(y * k))
    pw, ph = max(1, int(round(w * k))), max(1, int(round(h * k)))

    full = scr.grabWindow(0)                     # 整屏（物理像素）
    full_w, full_h = full.width(), full.height()
    px = max(0, min(px, full_w - 1))
    py = max(0, min(py, full_h - 1))
    pw = min(pw, full_w - px)
    ph = min(ph, full_h - py)
    if pw < 2 or ph < 2:
        raise ValueError("这一块太小了（或者跑到屏幕外面去了），给我宽一点的范围")

    cut = full.copy(px, py, pw, ph)

    # 先放大（小字才看得清），再压到 1280×800 以内
    big_w = int(pw * zoom)
    big_h = int(ph * zoom)
    fit = min(SHOT_MAX[0] / big_w, SHOT_MAX[1] / big_h, 1.0)
    if fit < 1.0:
        big_w, big_h = int(big_w * fit), int(big_h * fit)
    cut = cut.scaled(big_w, big_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%H%M%S")
    path = out_dir / f"zoom-{stamp}.png"
    if not cut.save(str(path), "PNG"):
        raise RuntimeError(f"存不下来：{path}")
    return {
        "path": str(path),
        "shot": (cut.width(), cut.height()),
        "region": (px, py, pw, ph),      # 屏幕物理像素
        "scale": float(LAST.get("scale") or 1.0),
        "foreground": foreground_title(),
    }
