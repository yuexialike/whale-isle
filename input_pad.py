"""单独接点击的小窗（InputPad）：只负责“她身上那块圆”能接住鼠标，什么都不画。

为什么要有：身体窗是分层透明的，她画在 figure 那扇窗上；那块像素的 alpha 是透明的，
Windows 的 hit-test 会直接穿过去，点到后面的浏览器/桌面。于是“看得见她”和“点得到她”
是两回事。pad 用圆遮罩把自己裁成她身体的形状，盖在最上面，把点击转给 Body 现成的
poke / 摸 / 拖拽逻辑。

但 pad 自己是 NOACTIVATE 的 Tool 窗，实测有时连 press 都收不到。所以这里还有第二条路：
**全局轮询**——16ms 读一次光标和左键状态，跟悬停“摸”同一条路；窗口收到就由窗口报，
窗口沉默就由轮询顶，两边用 `_down` 去重，一个按下周期只算一次。

谁调它：`body.py` 建分层小人的时候建一个；figure 移动/改大小/换包/显隐、
`set_behind_panels` 之后都调 `sync()` 重挂遮罩。
"""
from __future__ import annotations

import ctypes
import os
import time

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QMouseEvent, QPainter, QRegion
from PySide6.QtWidgets import QWidget

# 圆心漂移小于这个值就不重挂遮罩：每帧重算+setMask 会让窗口闪。
DRIFT_PX = 3.0


def hit_circles(hits) -> list[tuple[float, float, float]]:
    """从 layout.hit 里取圆的 (x, y, r)；坏项跳过，r<=0 的丢掉。"""
    out: list[tuple[float, float, float]] = []
    for item in hits or []:
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
            r = float(item.get("r"))
        except (AttributeError, TypeError, ValueError):
            continue
        if r > 0:
            out.append((x, y, r))
    return out


def mask_region(circles: list[tuple[float, float, float]]) -> QRegion:
    """多个圆并成一个 QRegion（一个圆是椭圆区域，多个就是 union）。

    坐标就是 figure 视图的 CSS px——它和 pad 的逻辑像素 1:1（视图 360×360 逻辑），
    所以这里不再乘 DPR：Qt 的遮罩用的是逻辑像素，乘了反而会偏。
    """
    region = QRegion()
    for x, y, r in circles:
        box = QRect(int(round(x - r)), int(round(y - r)), int(round(2 * r)), int(round(2 * r)))
        region = region.united(QRegion(box, QRegion.Ellipse))
    return region


def same_circles(a: list, b: list, drift: float = DRIFT_PX) -> bool:
    """两批圆是不是“没怎么动”（位置/半径都在 drift 内）。"""
    if len(a) != len(b):
        return False
    for (x1, y1, r1), (x2, y2, r2) in zip(a, b):
        if abs(x1 - x2) > drift or abs(y1 - y2) > drift or abs(r1 - r2) > drift:
            return False
    return True


def velocity(samples: list, window_ms: float = 120.0) -> tuple[float, float, float]:
    """用最近 window_ms 的 (t,x,y) 样本算速度（px/秒）。"""
    if len(samples) < 2:
        return 0.0, 0.0, 0.0
    t1, x1, y1 = samples[-1]
    t0, x0, y0 = samples[0]
    for s in samples:
        if (t1 - s[0]) * 1000.0 <= window_ms:
            t0, x0, y0 = s
            break
    dt = max(0.02, t1 - t0)
    vx = (x1 - x0) / dt
    vy = (y1 - y0) / dt
    return vx, vy, (vx * vx + vy * vy) ** 0.5


def velocity_last(samples: list) -> tuple[float, float, float]:
    """只用最后两个样本算瞬时速度。

    为什么：甩出去只有二三十毫秒，16ms 轮询在 120ms 窗口里会被前面的静止样本稀释，
    算出来永远不到 Body 的 1300 阈值；最后两拍才是“抬手那一下”的速度。
    """
    if len(samples) < 2:
        return 0.0, 0.0, 0.0
    t1, x1, y1 = samples[-1]
    t0, x0, y0 = samples[-2]
    dt = max(0.004, t1 - t0)
    vx = (x1 - x0) / dt
    vy = (y1 - y0) / dt
    return vx, vy, (vx * vx + vy * vy) ** 0.5


class InputPad(QWidget):
    def __init__(self, body) -> None:
        super().__init__(None)
        self._body = body
        self._applied: list[tuple[float, float, float]] = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("鲸屿 · 接点击")

        # layout.hit 是页面异步报上来的，第一次 sync 时常常还没有；每 200ms 看一次。
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.sync)
        self._timer.start()

        # 按下周期（窗口事件和全局轮询共用；_down 用来去重）
        self._down = False
        self._samples: list[tuple[float, float, float]] = []
        self._cursor = QCursor.pos          # 测试可以换成假的
        self._button = self._left_down      # 测试可以换成假的
        self._watch = QTimer(self)
        self._watch.setInterval(16)
        self._watch.timeout.connect(self._watch_tick)
        self._watch.start()

    # ------------------------------------------------------------ 遮罩
    def paintEvent(self, _ev) -> None:                   # noqa: N802 - Qt
        # 分层窗全透明像素会被 Windows 判成“点穿”，所以圆里填 alpha=1
        # （肉眼看不见，但 hit-test 认它）。形状由 setMask 的圆裁好。
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def set_topmost(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
        if self.isVisible():
            self.show()

    def hide_pad(self) -> None:
        self._applied = []
        self.hide()

    def sync(self) -> None:
        """让 pad 跟当前 figure 的位置/大小/圆心对齐；没东西可接就藏起来。"""
        body = self._body
        fig = getattr(body, "_fig", None)
        if fig is None or not body.figure_shown() or not fig.isVisible():
            self.hide_pad()
            return
        try:
            origin = fig.mapToGlobal(QPoint(0, 0))
            geo = QRect(origin, fig.size())
            if self.geometry() != geo:
                self.setGeometry(geo)
            circles = hit_circles((getattr(fig, "layout_state", None) or {}).get("hit"))
            if not circles:
                self.hide_pad()
                return
            if self.isVisible() and same_circles(self._applied, circles):
                return                       # 没漂，别重挂遮罩（会闪）
            self.setMask(mask_region(circles))
            self._applied = circles
            if not self.isVisible():
                self.show()
            self.raise_()
        except Exception:                    # noqa: BLE001
            pass

    # ------------------------------------------------------------ 诊断
    def pad_log_path(self):
        from pathlib import Path
        p = Path(__file__).resolve().parent / "data" / f"pad-{os.getpid()}.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _log(self, line: str) -> None:
        if not os.environ.get("JINGYU_PAD_LOG"):
            return
        try:
            with self.pad_log_path().open("a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except Exception:                    # noqa: BLE001
            pass

    def _center_global(self) -> str:
        """记一下「圆心在屏幕上的全局坐标」：和 QCursor.pos 同一个空间才能比。"""
        try:
            fig = self._body._fig
            hit = hit_circles((getattr(fig, "layout_state", None) or {}).get("hit"))[0]
            g = fig.mapToGlobal(QPoint(int(hit[0]), int(hit[1])))
            return f"{g.x()},{g.y()}"
        except Exception:                    # noqa: BLE001
            return "?"

    def _log_geom(self, why: str) -> None:
        """记账：失败时看遮罩/可见区/几何到底在哪。"""
        if not os.environ.get("JINGYU_PAD_LOG"):
            return
        try:
            self._log(f"{why} geom={self.geometry()} mask={self.mask().boundingRect()} "
                      f"visible={self.visibleRegion().boundingRect()} "
                      f"dpr={self.devicePixelRatioF()}")
        except Exception:                    # noqa: BLE001
            pass

    # ------------------------------------------------------------ 轮询
    @staticmethod
    def _left_down() -> int:
        """返回 GetAsyncKeyState(VK_LBUTTON) 原值：低字节 bit0=上次查询以来按过，
        高位 0x8000=现在按着。两个都要，短的点击才收得住。"""
        try:
            return int(ctypes.windll.user32.GetAsyncKeyState(0x01))
        except Exception:                    # noqa: BLE001
            return 0

    def _inside_hit(self, pos: QPoint) -> bool:
        """光标是不是在 figure 的 hit 圆里（全局坐标 → figure 局部 CSS px）。"""
        fig = getattr(self._body, "_fig", None)
        if fig is None or not fig.isVisible():
            return False
        try:
            o = fig.mapToGlobal(QPoint(0, 0))
            lx = float(pos.x() - o.x())
            ly = float(pos.y() - o.y())
            for x, y, r in hit_circles((getattr(fig, "layout_state", None) or {}).get("hit")):
                if (lx - x) ** 2 + (ly - y) ** 2 <= r * r:
                    return True
        except Exception:                    # noqa: BLE001
            return False
        return False

    def _ev(self, kind) -> QMouseEvent:
        pos = self._cursor()
        buttons = Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton
        return QMouseEvent(kind, QPointF(pos), QPointF(pos), Qt.LeftButton, buttons, Qt.NoModifier)

    def _begin_press(self) -> None:
        if self._down:
            return
        self._down = True
        self._samples = []
        body = self._body
        body._last_move = None
        body.mousePressEvent(self._ev(QEvent.MouseButtonPress))

    def _end_release(self) -> None:
        if not self._down:
            return
        self._down = False
        body = self._body
        try:
            vx, vy, speed = velocity_last(self._samples[-3:])
            self._log(f"release-speed {speed:.0f} samples={len(self._samples)}")
            if speed > 0:
                pos = self._cursor()
                dt = 0.01
                body._last_move = (time.monotonic() - dt,
                                   QPoint(int(pos.x() - vx * dt), int(pos.y() - vy * dt)))
        except Exception:                    # noqa: BLE001
            pass
        body.mouseReleaseEvent(self._ev(QEvent.MouseButtonRelease))

    def _watch_tick(self) -> None:
        body = self._body
        fig = getattr(body, "_fig", None)
        if fig is None or not fig.isVisible() or not body.figure_shown():
            if self._down:
                self._end_release()
            return
        s = int(self._button())
        held = bool(s & 0x8000)              # 现在按着
        clicked = bool(s & 0x0001)           # 这一拍里按下过（短点击也收）
        pos = self._cursor()
        if os.environ.get("JINGYU_PAD_LOG") and time.monotonic() - getattr(self, "_hb", 0.0) > 1.0:
            self._hb = time.monotonic()
            self._log(f"hb cursor={pos.x()},{pos.y()} inside={self._inside_hit(pos)} btn={s} "
                      f"hits={len(hit_circles((getattr(fig, 'layout_state', None) or {}).get('hit')))} "
                      f"figvis={fig.isVisible()} shown={body.figure_shown()} "
                      f"geom={self.geometry()} center={self._center_global()}")
        if not self._down and (held or clicked) and self._inside_hit(pos):
            self._begin_press()
            self._log_geom("poll-press")
            self._log(f"coords cursor={pos.x()},{pos.y()} "
                      f"center={self._center_global()} geom={self.geometry()} "
                      f"dpr={self.devicePixelRatioF()}")
        if not self._down:
            return
        if held:
            grab = getattr(body, "_grab", None)
            if grab is not None:
                body.move(pos - grab)
            now = time.monotonic()
            body._last_move = (now, pos)
            self._samples.append((now, float(pos.x()), float(pos.y())))
            del self._samples[:-8]
        else:
            self._end_release()

    # ------------------------------------------------------------ 窗口事件（有就报，没就靠轮询）
    def mousePressEvent(self, ev) -> None:               # noqa: N802 - Qt
        self._log(f"press {ev.globalPosition().toPoint().x()},{ev.globalPosition().toPoint().y()} "
                  f"capture={hex(ctypes.windll.user32.GetCapture())}")
        self.grabMouse()
        self._begin_press()

    def mouseMoveEvent(self, ev) -> None:                # noqa: N802 - Qt
        if not self._down:
            return

    def mouseReleaseEvent(self, ev) -> None:             # noqa: N802 - Qt
        self._log("release")
        self._end_release()
        try:
            self.releaseMouse()
        except Exception:                    # noqa: BLE001
            pass

    def mouseDoubleClickEvent(self, ev) -> None:         # noqa: N802 - Qt
        self._body.mouseDoubleClickEvent(ev)

    def closeEvent(self, event) -> None:                 # noqa: N802 - Qt
        self._watch.stop()
        self._applied = []
        super().closeEvent(event)
