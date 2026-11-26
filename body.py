"""身体：透明置顶窗口 + 小人 + 头顶气泡。

只负责「看起来像个人」：画自己、被拖、回底边、冒气泡。
不碰记忆、不碰模型——那些在 memory.py / llm.py 里。
"""
from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path

import touch_notes       # 3-4：碰触只记账，不叫醒模型

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

BODY_W, BODY_H = 220, 400      # 小人画布（桌宠本体约 210px 高，这里画到差不多一个量级）
BUBBLE_H = 150                 # 气泡预留高度
WINDOW_W = BODY_W + 160        # 窗口比小人宽，气泡才放得下
WINDOW_H = BODY_H + BUBBLE_H
PAD = 14                       # 气泡内边距
TAIL_CENTER, TAIL_FOLLOW = 70, 130   # 照抄 Coop tailAt
LINES_UP, LINES_GAP = 46, 8          # 照抄 Coop placeLines
# Coop pet.css 的浅色 token（气泡的「质感」）
SURFACE = "#FFFFFF"
BUBBLE_INK = "#1B1626"
SAID_BG = "#E6E9E7"
SAID_INK = "#1F2221"
SHADOW_INK = (27, 22, 38)
PAD_X, PAD_Y = 14, 10

POKE_LINES = ["欸？", "戳我干嘛哇。", "在的。", "别戳了，痒。", "嗯？找我有事？"]

# 20:10 加：鼠标停在身上算「摸」。连着摸会害羞，摸多了会炸毛。
PET_LINES_1 = ["欸嘿……", "摸头会让我眯眼睛的。", "……再摸一会儿也行。", "唔，好暖。"]
PET_LINES_2 = ["嗯……那里，对，就是那里。", "别停哇。", "耳朵后面，耳朵后面。"]
PET_LINES_3 = ["摸够啦！头发都乱了。", "哼，又不是毛绒玩具。", "再摸我就咬你。"]
# 甩出去落地太重会晕一会儿
THROW_LINES = ["哇——", "晕……让我缓两秒。", "你把我甩到哪儿去了哇。", "眼睛还在转圈……"]
# 11-02 浮空：被拎到半空松了手，就飘在那儿
FLOAT_LINES = ["欸，我飘起来了？", "脚底下空空的……有点慌。", "这样也挺好，看得远。",
               "松开手就别松太久哇。"]


def _load_figure(path: str, height: int):
    """把一张立绘读进来，白底抠成透明，缩到 height 高。失败就返回 None（退回画团子）。

    只抠**从边缘连进来的**那一片白：里面自己的白色衣服、高光不会被捅穿。
    """
    from collections import deque

    from PySide6.QtGui import QImage, QPixmap

    img = QImage(path)
    if img.isNull():
        return None
    img = img.scaledToHeight(int(height * 1.5), Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()

    def is_bg(c) -> bool:
        lo = min(c.red(), c.green(), c.blue())
        hi = max(c.red(), c.green(), c.blue())
        return lo > 214 and (hi - lo) < 26

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not seen[y * w + x] and is_bg(img.pixelColor(x, y)):
                seen[y * w + x] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not seen[y * w + x] and is_bg(img.pixelColor(x, y)):
                seen[y * w + x] = 1
                q.append((x, y))

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                i = ny * w + nx
                if not seen[i] and is_bg(img.pixelColor(nx, ny)):
                    seen[i] = 1
                    q.append((nx, ny))

    # 抠掉的那一片全透明；紧挨着它的边缘像素做一点羽化，免得剩一圈白边
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if seen[i]:
                c = img.pixelColor(x, y)
                c.setAlpha(0)
                img.setPixelColor(x, y, c)
            else:
                near = False
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and seen[ny * w + nx]:
                        near = True
                        break
                if near:
                    c = img.pixelColor(x, y)
                    c.setAlpha(170)
                    img.setPixelColor(x, y, c)

    # 裁掉四周的空白，让立绘填满画布（原来的图边上留白很多，不裁就显小）
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if not seen[y * w + x]:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if maxx > minx and maxy > miny:
        img = img.copy(minx, miny, maxx - minx + 1, maxy - miny + 1)

    img = img.scaledToHeight(height, Qt.SmoothTransformation)
    return QPixmap.fromImage(img)


FIG_H = BODY_H - 18            # 分层小人站的那块：脚底和立绘那条基线对齐
# 19:58 小人是画在 256 单位正方形里的，舞台只要不比方、或者太窄，人就被左右裁掉。
# 所以小人那扇窗给成正方形 360×360（S = 360/256 ≈ 1.4，人约 300px 高）。
FIG_W = 360
FIG_H = 360


def _foreground_is_fullscreen() -> bool:
    """前台那个窗口是不是糊满了整块屏（全屏游戏、全屏视频）。

    只问 Windows 三个数：前台窗口的矩形、它所在那块屏的矩形、窗口类名。
    出错一律当成「不是全屏」——宁可露脸，也别因为看不见的异常把自己藏没了。
    """
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h:
            return False
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Button"):
            return False

        wr = wintypes.RECT()
        if not u.GetWindowRect(h, ctypes.byref(wr)):
            return False

        MONITOR_DEFAULTTONEAREST = 2

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        mon = u.MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        mr = mi.rcMonitor
        slack = 2
        return (wr.left <= mr.left + slack and wr.top <= mr.top + slack
                and wr.right >= mr.right - slack and wr.bottom >= mr.bottom - slack)
    except Exception:
        return False


class Body(QWidget):
    def __init__(self, name: str = "鱼鱼", x_fraction: float = 0.5, figure_image: str = "",
                 roam: str = "free", layered: str = "", layered_theme: str = "dark",
                 float_height: int = 0, bubble_font: float = 1.0,
                 bubble_width: float = 1.0, bubble_seconds: float = 5.0,
                 hide_fullscreen: bool = False, scale: float = 1.0) -> None:
        super().__init__()
        self.name = name
        # 11-04 19:2x 设置里的「大小」：以前存进 cfg 没人读，是空壳。
        # 现在整扇窗（连分层小人那扇）按这个倍数缩放，画的时候 p.scale()，
        # 所有坐标还是按 WINDOW_W/H 这套逻辑像素算，鼠标用的是全局坐标，不用换算。
        self._scale = max(0.5, min(3.0, float(scale or 1.0)))
        # 11-02 习惯页：气泡的字号、宽度、停留时间（1.0 是原样）
        self._bubble_font = max(0.6, min(2.2, float(bubble_font or 1.0)))
        self._bubble_width = max(0.6, min(1.6, float(bubble_width or 1.0)))
        self._bubble_seconds = max(1.0, min(30.0, float(bubble_seconds or 5.0)))
        # 11-02 习惯页：有人在打全屏游戏 / 看全屏视频时，自己躲起来，别挡着
        self._hide_fs = bool(hide_fullscreen)
        self._fs_hidden = False
        self._fs_countdown = 0
        self._fig = None
        self._pad = None                # 3-4：单独接点击的圆垫片（身体只负责画）
        self._figure_on = True          # 「站在屏幕上」那道开关（11-04 17:45）
        self._fig_scheme = layered or ""
        if layered:
            self._make_layered(layered, layered_theme)
        self._x_frac = min(1.0, max(0.0, float(x_fraction)))
        self._roam = roam if roam in ("free", "calm", "off") else "free"
        # 11-02 浮空：离地高度（像素）。0 = 老样子贴着底边站。
        self._float_base = max(0, min(600, int(float_height or 0)))
        self._float_y = float(self._float_base)   # 现在悬的高度（缓动追着 _float_base 跑）
        self._float_dip = 0.0                     # 指针贴过来时临时下沉
        self._float_phase = 0.0                   # 悬着时轻轻上下漂的相位
        self._target_x: float | None = None
        self._speed = 120.0
        self._hold = False            # 分层小人坐着/睡着时别再走，不然它会滑着走
        self._face = 1
        self._pix = None
        if figure_image:
            self._pix = _load_figure(figure_image, BODY_H - 12)
        self._press_at = 0.0
        self._press_pos: QPoint | None = None
        self._hop = 0.0
        self._last_dbl = 0.0
        # 20:10 鼠标互动：摸（悬停一会儿）/ 甩出去（飞出去、落地太重会晕）
        self._hover_ticks = 0         # 指针在小人身上停了几帧
        self._pet_count = 0           # 连着被摸几下
        self._pet_last = 0.0
        self._pet_cool = 0.0         # 炸毛之后的冷却，别一直摸一直冒泡
        self._gait = 0.0             # 走路的步子相位（上下颠）
        self._tread_v = 0.0          # 告诉分层小人「正在迈步」的快慢（0 = 停）
        self._tread_face = 0
        self._last_move: tuple[float, QPoint] | None = None   # 算甩出去的初速
        self._fly: dict | None = None  # {"vx","vy"}：正在飞
        self._stun_until = 0.0        # 摔晕到什么时候，这之前不溜达
        self.on_double_click = None      # 设成可调用对象：双击身体时叫它
        self.on_right_click = None       # 右键：开对话页
        self._behind_panels = False      # 设置/对话页开着的时候让到下面去
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(*self._win_size())

        self._dragging = False
        self._grab: QPoint | None = None
        self._bob = 0.0
        self._bob_dir = 1
        self._text = ""
        self._text_left = 0          # 气泡还剩几帧
        self._said_lines: list[str] = []   # 人说的话，照 Coop placeLines 往上叠
        self._bubble_box = None      # 当前插值中的 (x,y,w,h)
        self._bubble_t0 = 0.0        # 出现动画起点
        self._bubble_fade = None     # 消失动画起点
        self._last_paint = time.monotonic()
        self._status = ""            # 小字：正在做什么
        self._status_left = 0        # 小字还剩几帧

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(60)

        # 自己溜达：每隔一阵挑个地方走过去
        self._roam_timer = QTimer(self)
        self._roam_timer.timeout.connect(self._maybe_roam)
        self._schedule_roam()

        self.snap_to_bottom()

    # ---------- 大小 ----------
    def _win_size(self) -> tuple[int, int]:
        s = self._scale
        return int(round(WINDOW_W * s)), int(round(WINDOW_H * s))

    def apply_scale(self, scale: float) -> None:
        """设置 → 习惯 →「大小」改了就地生效，不用重启。"""
        s = max(0.5, min(3.0, float(scale or 1.0)))
        if abs(s - self._scale) < 0.01:
            return
        self._scale = s
        self.resize(*self._win_size())
        self._fix_figure_size()
        self._place_figure()
        self.snap_to_bottom()
        self.update()

    def _fig_size(self) -> tuple[int, int]:
        s = self._scale
        return int(round(FIG_W * s)), int(round(FIG_H * s))

    def _fix_figure_size(self) -> None:
        """分层小人那扇窗跟着放大/缩小（它是个固定尺寸的小窗）。"""
        if self._fig is None:
            return
        w, h = self._fig_size()
        try:
            self._fig.setFixedSize(w, h)
            self._fig.set_size(w, h)
        except Exception:                              # noqa: BLE001
            pass

    # ---------- 站不站在屏幕上 ----------
    def show_figure(self, on: bool) -> None:
        """收 / 放她。

        11-04 17:45 的坑：分层小人（`figure_web`）是**另一扇窗**，
        光调 `self.hide()` 只收了自己那张，小人还站在那儿——
        所以他勾掉「站在屏幕上」，屏幕上照样有个人。要收就两扇一起收。
        """
        self._figure_on = bool(on)
        if on:
            self.show()
            if self._fig is not None:
                try:
                    self._fig.show()
                    self._place_figure()
                    if self._pad is not None:
                        self._pad.sync()
                except Exception:
                    pass
            self.raise_()
        else:
            if self._fig is not None:
                try:
                    self._fig.hide()
                except Exception:
                    pass
            if self._pad is not None:
                self._pad.hide_pad()      # 3-4：人收起来，接点击的垫片也收
            self.hide()

    def figure_shown(self) -> bool:
        return bool(getattr(self, "_figure_on", True))

    # ---------- 让位给正经窗户 ----------
    def set_behind_panels(self, on: bool) -> None:
        """设置页 / 对话页开着的时候，别站在人家前面。

        身体一直是 topmost——站在所有窗口上面本来就是这个桌宠的样子。
        可设置页不是 topmost，于是被她整个盖住：11-02 13:17 月下看气泡，只看到半个。
        做法：面板开着的时候摘掉 topmost，关掉再挂回去。改 flag 会让窗口隐一次，所以存位置、再露出来。
        """
        on = bool(on)
        if on == self._behind_panels:
            return
        self._behind_panels = on
        pos = self.pos()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, not on)
        if self.figure_shown():            # 「站在屏幕上」关着的时候别把她叫回来
            self.show()
            self.move(pos)
        # 分层小人是一扇单独的窗（figure_web），不跟着一起放，她照样压在上面
        if self._fig is not None:
            try:
                from PySide6.QtCore import Qt as _Qt
                self._fig.setWindowFlag(_Qt.WindowStaysOnTopHint, not on)
                if self.figure_shown():
                    self._fig.show()
                    self._place_figure()
            except Exception:
                pass
        # 3-4：接点击的垫片跟着摘/挂 topmost，不然面板开着时它隔着面板吃点击
        if self._pad is not None:
            self._pad.set_topmost(not on)
            self._pad.sync()
        if not on and self.figure_shown():
            self.raise_()

    # ---------- 走路 ----------
    def walk_to(self, frac: float, run: bool = False) -> None:
        """沿屏幕底边走到某个横向位置（0 最左、1 最右）。"""
        r = self.screen_rect()
        frac = min(1.0, max(0.0, float(frac)))
        self._speed = 320.0 if run else 120.0
        self._target_x = r.left() + (r.width() - self.width()) * frac

    def _schedule_roam(self) -> None:
        if self._roam == "off":
            self._roam_timer.stop()
            return
        base = (7000, 16000) if self._roam == "free" else (20000, 45000)
        self._roam_timer.start(random.randint(*base))

    def _maybe_roam(self) -> None:
        self._schedule_roam()
        if self._target_x is not None or self._dragging or self._text or self._hold:
            return
        if self._fly is not None or time.monotonic() < self._stun_until:
            return                                  # 还在飞 / 摔晕着，别溜达
        # 20:58 她自己睡着的时候别硬把她拖去溜达（月下看见的「坐着也能走」）；
        # 只是坐着的，让 kit 那边的 tread 先把她叫起来再走。
        mode = (self._fig.layout_state or {}).get("mode") if self._fig is not None else None
        if mode == "sleep":
            return
        if random.random() < 0.25:            # 有时候只是站一会儿、蹦一下
            if random.random() < 0.5:
                self._hop = 0.6
            return
        self.walk_to(random.uniform(0.04, 0.86))

    def _step_walk(self) -> None:
        if self._target_x is None or self._hold or self._fly is not None:
            self._tread(0.0)
            return
        cur = float(self.x())
        dx = self._target_x - cur
        step = self._speed * 0.06
        self._face = 1 if dx > 0 else -1
        # 20:45 迈步：窗口在搬，脚也得迈（kit 的 tread 档），不然就是贴图在滑
        self._tread(1.0)
        # 20:22 走路有节奏：整扇窗跟着步子上下颠一点（脚被裙子挡着，不动起来就像滑）
        base_y = self.screen_rect().bottom() - WINDOW_H + 6 - self._float_offset()
        self._gait += 1
        bob = -abs(math.sin(self._gait * 0.55)) * 2.5
        if abs(dx) <= step:
            self.move(int(self._target_x), int(base_y))
            self._target_x = None
            self._gait = 0.0
            self._tread(0.0)
        else:
            self.move(int(cur + (step if dx > 0 else -step)), int(base_y + bob))
        r = self.screen_rect()
        self._x_frac = (self.x() - r.left()) / max(1.0, r.width() - self.width())

    # ---------- 位置 ----------
    def _tread(self, v: float) -> None:
        """20:45 告诉分层小人「正在迈步」，0 = 停。

        她是 Python 搬着窗口走的，页面只有一块 360 宽的舞台，kit 的 walk 用不上；
        给了这个档，脚才会迈。facing 变了才补一条 place，别每帧都发。
        """
        if self._fig is None:
            return
        if abs(v - self._tread_v) < 1e-3 and self._face == self._tread_face:
            return
        self._tread_v = v
        self._tread_face = self._face
        try:
            self._fig.set_tread(v, self._face)
        except Exception:
            pass

    def screen_rect(self):
        scr = self.screen() or QGuiApplication.primaryScreen()
        return QRectF(scr.availableGeometry())

    def snap_to_bottom(self) -> None:
        r = self.screen_rect()
        x = int(r.left() + (r.width() - self.width()) * self._x_frac)
        y = int(r.bottom() - self.height() + 6 - self._float_offset())
        self.move(x, y)

    # ---------- 分层小人（会呼吸、会做动作的那套） ----------
    def _make_layered(self, scheme: str, theme: str) -> None:
        """把 figure_web 那个分层小人挂到身体上。

        立绘画在一张静态图上；分层小人是一个 QWebEngineView，自己会呼吸、会做表情动作。

        ⚠️ 19:11 试过把它当**子控件**塞进身体那扇窗（Tool + 不接受焦点 + 半透明）——
        log 里 ready=True、动作也送得进去，可屏幕上什么都不画。所以改成
        **独立的无边框小窗**：和 `figure_web.preview()` 一模一样的窗口属性（那条路亲眼验过能显示），
        位置由 `_place_figure()` 跟着身体走。戳和拖还是身体自己接（小人这扇窗是鼠标穿透的）。
        """
        try:
            from PySide6.QtCore import Qt as _Qt
            from figure_web import FigureWeb

            self._fig = FigureWeb(scheme=scheme, theme=theme)
            self._fig.setWindowFlags(
                _Qt.FramelessWindowHint | _Qt.WindowStaysOnTopHint | _Qt.Tool
                | _Qt.WindowTransparentForInput | _Qt.WindowDoesNotAcceptFocus
            )
            self._fig.setAttribute(_Qt.WA_TranslucentBackground, True)
            self._fig.setAttribute(_Qt.WA_ShowWithoutActivating, True)
            self._fix_figure_size()
            self._fig.show()
            # 19:26 踩到：光 resize 不够，窗口被布局撑高了，人比窗口还大 → 左右被切掉一块。
            # 尺寸定死，图上就按这个窗口缩放。19:52 宽度也按小人的比例给足（FIG_W）。
            self._fig.setFixedSize(*self._fig_size())
            self._place_figure()
            # 3-4：身体是分层透明的，hit-test 会穿过去；盖一个只接点击的圆垫片。
            try:
                from input_pad import InputPad
                self._pad = InputPad(self)
                self._pad.sync()
            except Exception:                   # noqa: BLE001 - 垫片坏了不影响画面
                self._pad = None
            self._log(f"分层小人窗口 {self._fig.width()}x{self._fig.height()}（身体 {WINDOW_W}x{WINDOW_H}）")
        except Exception:                       # 装不上就退回立绘，不挡开机
            import traceback
            self._fig = None
            from pathlib import Path
            try:
                p = Path(__file__).resolve().parent / "data" / "figure_error.log"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass

    def _place_figure(self) -> None:
        """小人那扇窗贴着身体的脚：横向居中在身体那块，脚底和立绘基线同高。"""
        if self._fig is None:
            return
        try:
            g = self.geometry()
            fw, fh = self._fig_size()
            x = g.x() + (self.width() - fw) // 2
            y = g.y() + self.height() - int(round(18 * self._scale)) - fh   # 脚底和立绘基线同高
            if (self._fig.x(), self._fig.y()) != (x, y):
                self._fig.move(x, y)
            if self._pad is not None:
                self._pad.sync()          # 3-4：小人挪了，接点击的圆也跟着挪
        except Exception:
            pass

    def closeEvent(self, event) -> None:                 # noqa: N802 - Qt
        if self._pad is not None:
            try:
                self._pad.close()
            except Exception:
                pass
            self._pad = None
        if self._fig is not None:
            try:
                self._fig.close()
            except Exception:
                pass
            self._fig = None
        super().closeEvent(event)

    def act(self, word: str) -> bool:
        """做一个动作（jump / wave / sit / 表情词…）。返回做没做成。

        18:47 月下看到的问题：说了「坐下」，可它还在往下走——窗口在移，人坐着，
        看着就是「坐着平移」。所以坐下/睡着这一类把身体钉住，站起来/别的不动，
        等下一次站起（stand / jump / walk / 别的动作）再松开。
        """
        if self._fig is None:
            return False
        # 3-4：只认当前形象包 figure.json 里有的 id；包里没有的词不往 figure.js 送。
        try:
            import figure_vocab
            if not figure_vocab.known(word):
                self._log(f"形象包不认这个动作：{word}")
                return False
        except Exception:                            # noqa: BLE001
            pass
        if os.environ.get("JINGYU_BODY_LOG"):
            # 只给真机验收看「动作有没有真送出去」：每个进程一个文件。
            try:
                p = Path(__file__).resolve().parent / "data" / f"body-{os.getpid()}.log"
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} {word}\n")
            except Exception:                        # noqa: BLE001
                pass
        try:
            if word in ("sit", "sleep"):
                self._target_x = None          # 手头这段路也停下
                self._hold = True
            elif word in ("stand", "jump", "hop", "walk", "run", "spin", "dance"):
                self._hold = False
            self._fig.do(word)
            return True
        except Exception:
            return False

    def set_scheme(self, scheme: str, fade: float = 0.25) -> bool:
        if self._fig is None:
            return False
        try:
            self._fig.set_scheme(scheme, fade)
            self._fig_scheme = scheme
            return True
        except Exception:
            return False

    def layered(self) -> bool:
        """现在是不是分层小人（而不是一张立绘）。"""
        return self._fig is not None

    # ---------- 说话 ----------
    def say(self, text: str, seconds: float | None = None) -> None:
        self._text = (text or "").strip()
        self._bubble_t0 = time.monotonic()
        self._bubble_fade = None
        self._bubble_box = None
        base = self._bubble_seconds if seconds is None else float(seconds)
        # 习惯页里调的停留时间会按比例缩放每一句（原基准 5 秒）
        secs = base * (self._bubble_seconds / 5.0) if seconds is not None else base
        self._text_left = int(max(1.0, secs) * 1000 / 60) if self._text else 0
        self.update()

    def is_speaking(self) -> bool:
        return bool(self._text)

    # ---------- 小字：正在做什么 ----------
    def status(self, text: str, seconds: float = 4.0) -> None:
        """头顶一行小灰字。说话是小字之外的另一件事：小字表示「正在做事」。"""
        self._status = (text or "").strip()
        self._status_left = int(seconds * 1000 / 60) if self._status else 0
        self.update()

    def clear_status(self) -> None:
        self._status, self._status_left = "", 0
        self.update()

    def is_busy(self) -> bool:
        return bool(self._status)

    # ---------- 动画 ----------
    def _step_fullscreen(self) -> None:
        """全屏就躲、退出全屏就回来。只在真的换了状态时动窗口。"""
        fs = _foreground_is_fullscreen()
        if fs and not self._fs_hidden:
            self._fs_hidden = True
            self.hide()
        elif not fs and self._fs_hidden:
            self._fs_hidden = False
            if self.figure_shown():
                self.show()

    def _on_tick(self) -> None:
        try:
            self._tick_once()
        except Exception:                      # 别让一帧的错炸掉整个窗口
            import traceback
            from pathlib import Path
            try:
                p = Path(__file__).resolve().parent / "data" / "tick_error.log"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass

    def _tick_once(self) -> None:
        # 全屏时躲起来：每 20 帧（约 1.2 秒）问一次 Windows，别每帧都问
        if self._hide_fs:
            self._fs_countdown -= 1
            if self._fs_countdown <= 0:
                self._fs_countdown = 20
                self._step_fullscreen()
        self._step_flight()
        self._step_walk()
        self._step_hover()
        self._step_float()
        self._bob += 0.05 * self._bob_dir
        if self._bob > 1.0:
            self._bob, self._bob_dir = 1.0, -1
        elif self._bob < -1.0:
            self._bob, self._bob_dir = -1.0, 1
        if self._text_left > 0:
            self._text_left -= 1
            if self._text_left == 0 and self._text:
                self._bubble_fade = time.monotonic()
        if self._status_left > 0:
            self._status_left -= 1
            if self._status_left == 0:
                self._status = ""
        if self._hop > 0.0:
            self._hop = max(0.0, self._hop - 0.06)
        self._place_figure()
        self.update()

    def poke(self) -> None:
        """被戳一下：蹦一下，回一句。"""
        touch_notes.record("poke")          # 3-4：只记账，不叫醒模型
        self._hop = 1.0
        self.act(random.choice(["surprised", "hop", "pout", "shy"]))
        self.say(random.choice(POKE_LINES), 3.0)

    # ---------- 摸：指针停在她身上 ----------
    def _pointer_on_body(self) -> bool:
        """指针是不是真的停在她身上。

        20:22 踩到：一开始用「窗口矩形」判，窗口是 360×360 的大方块，指针停在她头顶那片
        空白里也会一直触发，成了自动刷屏。改用页面报上来的 layout.hit 圆（她的身体范围，
        舞台坐标 = 窗口内的 CSS 像素，和窗口逻辑坐标 1:1）。
        """
        pos = QCursor.pos()
        if self._fig is None:
            return self.geometry().contains(pos)
        try:
            g = self._fig.geometry()
            lay = getattr(self._fig, "layout_state", None)
            if not lay:
                return g.contains(pos)
            lx = pos.x() - g.x()
            ly = pos.y() - g.y()
            for h in lay.get("hit") or []:
                r = float(h.get("r") or 0)
                if r > 0 and (lx - float(h["x"])) ** 2 + (ly - float(h["y"])) ** 2 <= r * r:
                    return True
            return False
        except Exception:
            return False

    def _step_hover(self) -> None:
        if self._dragging or self._fly is not None:
            self._hover_ticks = 0
            return
        if time.monotonic() < self._pet_cool:
            self._hover_ticks = 0
            return
        if not self._pointer_on_body():
            self._hover_ticks = 0
            if time.monotonic() - self._pet_last > 12.0:
                self._pet_count = 0          # 隔久了，重新从头害羞
            return
        self._hover_ticks += 1
        # 停够约 1 秒才认；两次之间至少隔 2.2 秒，不然一停就刷屏
        if self._hover_ticks >= 17 and time.monotonic() - self._pet_last > 2.2:
            self._pet()

    def _pet(self) -> None:
        """被摸一下：先害羞，再黏人，摸第三下炸毛。"""
        touch_notes.record("pet")            # 3-4：只记账
        self._hover_ticks = 0
        self._pet_last = time.monotonic()
        self._pet_count += 1
        n = self._pet_count
        if n >= 3:
            self._pet_count = 0
            self._pet_cool = time.monotonic() + 25.0     # 摸够了，安静一会儿
            self.act(random.choice(["pout", "flustered"]))
            self.say(random.choice(PET_LINES_3), 3.0)
        elif n == 2:
            self.act("love")
            self.say(random.choice(PET_LINES_2), 3.0)
        else:
            self.act("shy")
            self.say(random.choice(PET_LINES_1), 3.0)

    # ---------- 甩出去：飞一段，落地太重会晕 ----------
    def _start_flight(self, vx: float, vy: float) -> None:
        touch_notes.record("throw")          # 3-4：甩出去记一笔
        self._target_x = None
        self._fly = {"vx": vx, "vy": vy}

    def _step_flight(self) -> None:
        if self._fly is None:
            return
        f = self._fly
        dt = 0.06
        x = self.x() + f["vx"] * dt
        y = self.y() + f["vy"] * dt
        f["vy"] += 2400.0 * dt                     # 重力，飞着往下坠
        r = self.screen_rect()
        x = max(r.left() - self.width() * 0.3, min(r.right() - self.width() * 0.7, x))
        ground = r.bottom() - self.height() + 6
        if y >= ground and f["vy"] > 0:
            impact = f["vy"]
            self._fly = None
            self.move(int(x), int(ground))
            self._x_frac = (self.x() - r.left()) / max(1.0, r.width() - self.width())
            self._x_frac = min(1.0, max(0.0, self._x_frac))
            self.snap_to_bottom()
            if impact > 1500.0:                     # 甩得凶，落地摔晕几秒
                touch_notes.record("crash")         # 3-4：摔晕记一笔
                self._stun_until = time.monotonic() + 3.0
                self._hop = 0.0
                self.act("dizzy")
                self.say(random.choice(THROW_LINES), 4.0)
            return
        self.move(int(x), int(y))
        r2 = self.screen_rect()
        self._x_frac = (self.x() - r2.left()) / max(1.0, r2.width() - self.width())

    # ---------- 浮空：离地悬着（11-02 平凡提的「人偶能不能浮空」） ----------
    def set_float_height(self, px: int) -> None:
        """改悬停高度，0 = 回到底边。设置页保存、外面调都走这里。"""
        self._float_base = max(0, min(600, int(px or 0)))

    def apply_look(self, cfg: dict) -> None:
        """设置页一存就把这几样换到身上，不用重启（11-04 17:39 月下要的）。

        走得动、气泡、浮空、大小这四样当场换；立绘还是得重开。
        """
        roam = str(cfg.get("roam", "free") or "free")
        if roam in ("free", "calm", "off") and roam != self._roam:
            self._roam = roam
            self._schedule_roam()
        try:
            self._bubble_font = max(0.6, min(2.2, float(cfg.get("bubble_font", 1.0) or 1.0)))
            self._bubble_width = max(0.6, min(1.6, float(cfg.get("bubble_width", 1.0) or 1.0)))
            self._bubble_seconds = max(1.0, min(30.0, float(cfg.get("bubble_seconds", 5.0) or 5.0)))
        except (TypeError, ValueError):
            pass
        if "float_height" in cfg:
            self.set_float_height(int(cfg.get("float_height") or 0))
        if "scale" in cfg:
            self.apply_scale(float(cfg.get("scale") or 1.0))
        self.update()

    def _float_wave(self) -> float:
        """悬着的时候轻轻上下漂一点，看着像浮在水里。"""
        if self._float_y < 2.0:
            return 0.0
        return math.sin(self._float_phase) * 2.2

    def _float_offset(self) -> float:
        return max(0.0, self._float_y + self._float_dip + self._float_wave())

    def _step_float(self) -> None:
        """每帧把纵向位置往「该悬的高度」挪一点。

        互动：指针停在她身上时，她会往下沉一点凑近你；手一拿开又飘回去。
        """
        if self._dragging or self._fly is not None:
            self._float_dip = 0.0
            return
        want = 0.0
        if self._float_base > 0 and self._pointer_on_body():
            want = -min(16.0, self._float_y * 0.5)
        self._float_dip += (want - self._float_dip) * 0.12
        self._float_y += (float(self._float_base) - self._float_y) * 0.10
        if abs(self._float_base - self._float_y) < 0.3:
            self._float_y = float(self._float_base)
        if self._float_y > 1.0 or abs(self._float_dip) > 0.5:
            self._float_phase += 0.045
            r = self.screen_rect()
            y = int(r.bottom() - self.height() + 6 - self._float_offset())
            if y != self.y():
                self.move(self.x(), y)

    # ---------- 画 ----------
    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        # 整块画布按「大小」倍数放大：下面所有坐标都还是 WINDOW_W/H 这套逻辑像素
        p.scale(self._scale, self._scale)

        if self._status:
            self._draw_status(p, self._status)

        if self._text or self._said_lines:
            self._draw_bubble(p, self._text)

        p.save()
        p.translate((WINDOW_W - BODY_W) / 2, BUBBLE_H)
        self._draw_body(p)
        p.restore()

    def _draw_status(self, p: QPainter, text: str) -> None:
        """左上角一行小灰字：正在做什么。不挡身体，也不跟气泡抢地方。"""
        font = QFont("Microsoft YaHei", 9)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = min(WINDOW_W - 16, fm.horizontalAdvance(text) + 18)
        h = fm.height() + 8
        x, y = 8.0, 4.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 225))
        p.drawRoundedRect(QRectF(x, y, w, h), 8, 8)
        p.setPen(QColor(90, 100, 120))
        p.drawText(QRectF(x + 9, y + 4, w - 18, h - 8), Qt.AlignVCenter | Qt.AlignLeft, text)

    def add_said_line(self, text: str) -> None:
        """人说的话：照 Coop 的 said 行往上叠，最多 3 条。"""
        t = (text or "").strip()
        if not t:
            return
        self._said_lines.append(t)
        del self._said_lines[:-3]
        self.update()

    def _head_anchor(self) -> tuple[float, float]:
        """Coop 的 a = layout.bubble：分层小人直接读 figure 的头部点。"""
        try:
            if self._fig is not None and isinstance(self._fig.layout_state, dict):
                b = self._fig.layout_state.get("bubble") or {}
                if "x" in b and "y" in b:
                    # 用身体窗内的逻辑偏移，不要用屏幕几何（DPI 下会差 1.5 倍）
                    ox = (self.width() - self._fig.width()) / 2
                    oy = self.height() - 18 * self._scale - self._fig.height()
                    return (float(ox + b["x"]), float(oy + b["y"]))
        except Exception:                            # noqa: BLE001
            pass
        if self._pix is not None:
            return WINDOW_W / 2, BUBBLE_H + BODY_H - 18 - self._pix.height()
        return WINDOW_W / 2, float(BUBBLE_H + 24)

    @staticmethod
    def _tail_at(bw: float, x: float) -> float:
        """照抄 Coop tailAt：宽 70 以内跟头，70→130 逐渐跟，夹 22..bw-22。"""
        k = max(0.0, min(1.0, (bw - TAIL_CENTER) / (TAIL_FOLLOW - TAIL_CENTER)))
        return bw / 2 + (min(max(x, 22), bw - 22) - bw / 2) * k

    @staticmethod
    def _shadow(p: QPainter, x: float, y: float, w: float, h: float,
                blur: float = 22.0, dy: float = 8.0, alpha: int = 31) -> None:
        """Coop box-shadow: 0 8px 22px rgba(27,22,38,.12)，用多层低透明度近似模糊。"""
        for i in range(int(blur), 0, -2):
            a = max(1, int(alpha * (1 - i / blur) ** 1.6 / 3))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(SHADOW_INK[0], SHADOW_INK[1], SHADOW_INK[2], a))
            p.drawRoundedRect(QRectF(x - i / 3, y + dy - i / 3,
                                     w + 2 * i / 3, h + 2 * i / 3), 18 + i / 3, 18 + i / 3)

    def _draw_said(self, p: QPainter, fm: QFontMetrics, head_x: float, head_y: float,
                   box: tuple[float, float, float, float] | None) -> None:
        if not self._said_lines:
            return
        max_w = int(260 * self._bubble_width)
        gap = LINES_GAP
        cx = box[0] + box[2] / 2 if box else head_x
        bottom = box[1] - gap if box else head_y - LINES_UP
        for idx, text in enumerate(reversed(self._said_lines)):
            rect = fm.boundingRect(0, 0, max_w - PAD_X * 2, 220, Qt.TextWordWrap, text)
            w = max(46, min(max_w, rect.width() + PAD_X * 2))
            h = rect.height() + PAD_Y * 2
            left = min(max(cx - w / 2, 10), max(10, WINDOW_W - w - 10))
            top = max(8, bottom - h)
            p.save()
            p.setOpacity(1.0 if idx == 0 else 0.62)   # Coop .said.older
            self._shadow(p, left, top, w, h, blur=14, dy=4, alpha=31)
            p.setPen(Qt.NoPen)                       # .said 的 border-color: transparent
            p.setBrush(QColor(SAID_BG))
            p.drawRoundedRect(QRectF(left, top, w, h), 18, 18)
            p.setPen(QColor(SAID_INK))
            p.drawText(QRectF(left + PAD_X, top + PAD_Y,
                              w - PAD_X * 2, h - PAD_Y * 2), Qt.TextWordWrap, text)
            p.restore()
            bottom = top - gap

    def _draw_bubble(self, p: QPainter, text: str) -> None:
        font = QFont("Microsoft YaHei")
        font.setPixelSize(max(8, int(round(14.5 * self._bubble_font))))
        p.setFont(font)
        fm = QFontMetrics(font)
        s = max(0.1, self._scale)
        head_x, head_y = self._head_anchor()
        # Coop: max-width 300 * bubble-size; no face flip, just shift 26 px.
        max_w = int(300 * self._bubble_width)
        try:
            r0 = self.screen_rect()
            max_w = min(max_w, int(max(80.0, (r0.width() - 14) / s)))
        except Exception:                            # noqa: BLE001
            pass
        target = None
        if text:
            rect = fm.boundingRect(0, 0, max_w - PAD_X * 2, 220, Qt.TextWordWrap, text)
            w = max(46, min(max_w, rect.width() + PAD_X * 2))
            h = rect.height() + PAD_Y * 2
            # exact Coop place():
            x = head_x - w / 2 + (self._face or 1) * 26
            y = head_y - h - 18
            # keep inside this window and on screen (newhouse's window is the stage)
            x = min(max(x, 10), max(10, WINDOW_W - w - 10))
            try:
                r = self.screen_rect()
                win_l, win_t = float(self.x()), float(self.y())
                lo = max(10.0, (r.left() + 6 - win_l) / s)
                hi = min(WINDOW_W - w - 10, (r.right() + 1 - 6 - win_l) / s - w)
                if hi >= lo:
                    x = min(max(x, lo), hi)
                y = max(y, (r.top() + 6 - win_t) / s)
            except Exception:                        # noqa: BLE001
                pass
            y = max(8, y)
            target = (x, y, w, h)

        # Coop placeLines 的 dt*12 插值：位置和宽高都往目标靠，不是啪一下贴上去。
        now = time.monotonic()
        dt = max(0.001, min(0.20, now - self._last_paint))
        self._last_paint = now
        box = None
        if target is not None:
            if self._bubble_box is None:
                self._bubble_box = target
            else:
                k = min(1.0, dt * 12.0)
                cur = self._bubble_box
                self._bubble_box = tuple(cur[i] + (target[i] - cur[i]) * k for i in range(4))
            box = self._bubble_box
        else:
            self._bubble_box = None

        self._draw_said(p, fm, head_x, head_y, box)
        if not text:
            return

        # Coop .pop: scale(.5)->1 / opacity 0->1, .26s cubic-bezier(.3,1.5,.5,1)
        pop = min(1.0, max(0.0, (now - self._bubble_t0) / 0.26)) if self._bubble_t0 else 1.0
        e = pop - 1.0
        ease = 1.0 + 2.70158 * e * e * e + 1.70158 * e * e
        scale = 0.5 + 0.5 * ease
        alpha = pop
        if self._bubble_fade is not None:
            fd = min(1.0, max(0.0, (now - self._bubble_fade) / 0.40))
            alpha *= (1.0 - fd)
            if fd >= 1.0:
                self._text = ""
                self._bubble_fade = None
                self._bubble_box = None
                return
        if alpha <= 0.01:
            return
        x, y, w, h = box
        # tail: exact Coop tailAt on head relative to bubble left
        tail = self._tail_at(w, head_x - x)
        tip_x = x + tail

        p.save()
        p.setOpacity(alpha)
        p.translate(tip_x, y + h)
        p.scale(scale, scale)
        p.translate(-tip_x, -(y + h))

        # Coop box-shadow: 0 8px 22px rgba(27,22,38,.12)
        self._shadow(p, x, y, w, h, blur=22, dy=8, alpha=31)
        # body: 2.5px solid #1B1626, radius 18, surface
        p.setPen(QPen(QColor(BUBBLE_INK), 2.5))
        p.setBrush(QColor(SURFACE))
        p.drawRoundedRect(QRectF(x, y, w, h), 18, 18)

        # double-triangle tail: pet.css paths, 22 x 11.5, left = tail - 13.5, bottom = -11
        ox, oy = x + tail - 13.5, y + h - 11
        outer = QPainterPath()
        outer.moveTo(ox + 0.75, oy + 1.25)
        outer.lineTo(ox + 8.9, oy + 9.4)
        outer.quadTo(ox + 11, oy + 11.5, ox + 13.1, oy + 9.4)
        outer.lineTo(ox + 21.25, oy + 1.25)
        outer.closeSubpath()
        inner = QPainterPath()
        inner.moveTo(ox + 3.04, oy)
        inner.lineTo(ox + 10.53, oy + 7.49)
        inner.quadTo(ox + 11, oy + 7.96, ox + 11.47, oy + 7.49)
        inner.lineTo(ox + 18.96, oy)
        inner.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BUBBLE_INK))
        p.drawPath(outer)
        p.setBrush(QColor(SURFACE))
        p.drawPath(inner)

        p.setPen(QColor(BUBBLE_INK))
        p.drawText(QRectF(x + PAD_X, y + PAD_Y, w - PAD_X * 2, h - PAD_Y * 2),
                   Qt.TextWordWrap, text)
        p.restore()

    def _draw_body(self, p: QPainter) -> None:
        if self._fig is not None:                 # 分层小人自己就是个窗口里的控件，别在它上面画
            return
        lift = self._bob * (6.0 if self._target_x is not None else 3.0) - self._hop * 16.0
        cx = BODY_W / 2
        base = BODY_H - 18

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QRectF(cx - 46, base - 8, 92, 16))

        p.translate(0, -lift)

        if self._pix is not None:                 # 有立绘就用立绘
            w, h = self._pix.width(), self._pix.height()
            if self._face < 0:                    # 往左走就翻个面
                p.save()
                p.translate(cx, 0)
                p.scale(-1, 1)
                p.drawPixmap(int(-w / 2), int(base - h), self._pix)
                p.restore()
            else:
                p.drawPixmap(int(cx - w / 2), int(base - h), self._pix)
            return

        path = QPainterPath()
        path.moveTo(cx - 26, base - 60)
        path.quadTo(cx - 74, base - 70, cx - 66, base - 112)
        path.quadTo(cx - 52, base - 92, cx - 22, base - 84)
        p.setBrush(QColor(120, 180, 240))
        p.setPen(QPen(QColor(60, 110, 180), 3))
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(150, 200, 245))
        p.drawRoundedRect(QRectF(cx - 46, base - 128, 92, 118), 44, 44)

        p.setBrush(QColor(170, 212, 250))
        p.drawEllipse(QRectF(cx - 40, base - 214, 80, 80))

        hair = QPainterPath()
        hair.addEllipse(QRectF(cx - 42, base - 220, 84, 62))
        p.setBrush(QColor(70, 120, 210))
        p.drawPath(hair)

        p.setPen(QPen(QColor(70, 120, 210), 4))
        p.drawLine(int(cx), int(base - 220), int(cx + 10), int(base - 244))

        p.setPen(QPen(QColor(40, 60, 90), 4))
        p.drawLine(int(cx - 20), int(base - 180), int(cx - 12), int(base - 180))
        p.drawLine(int(cx + 12), int(base - 180), int(cx + 20), int(base - 180))

    # ---------- 拖 / 戳 ----------
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._grab = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = ev.globalPosition().toPoint()
            self._press_at = time.monotonic()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging and self._grab is not None:
            pos = ev.globalPosition().toPoint()
            self._last_move = (time.monotonic(), pos)
            self.move(pos - self._grab)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if self._dragging:
            self._dragging = False
            self._grab = None
            moved = 999.0
            if self._press_pos is not None:
                moved = (ev.globalPosition().toPoint() - self._press_pos).manhattanLength()
            quick = (time.monotonic() - self._press_at) < 0.6
            # 20:14 甩出去：抬手那一下的速度够快，就带着惯性飞出去，落地太重会晕
            pos = ev.globalPosition().toPoint()
            vx = vy = 0.0
            if self._last_move is not None:
                t0, p0 = self._last_move
                dt = max(0.02, time.monotonic() - t0)
                vx = (pos.x() - p0.x()) / dt
                vy = (pos.y() - p0.y()) / dt
            self._last_move = None
            speed = (vx * vx + vy * vy) ** 0.5
            if moved >= 8 and speed > 1300.0:
                k = 0.55 * min(1.0, 4000.0 / speed)      # 初速封顶，别飞到天外
                self._start_flight(vx * k, vy * k)
            elif moved < 8 and quick and (time.monotonic() - self._last_dbl) > 0.5:
                self.poke()
            else:
                # 放哪儿就在哪儿：横向记成 x_frac；纵向——拎得离地够高就松手悬在那儿（11-02 浮空）
                touch_notes.record("drop")          # 3-4：拎起来再放下，记一笔
                r = self.screen_rect()
                self._x_frac = (self.x() - r.left()) / max(1.0, r.width() - self.width())
                self._x_frac = min(1.0, max(0.0, self._x_frac))
                self._target_x = None
                ground = r.bottom() - self.height() + 6
                lift = ground - self.y()
                if lift > 40:
                    was = self._float_base
                    self.set_float_height(int(min(lift, r.height() * 0.55)))
                    self._float_y = float(self._float_base)      # 原地接手，别跳一下
                    if was <= 0:
                        self.act(random.choice(["surprised", "flustered"]))
                        self.say(random.choice(FLOAT_LINES), 3.0)
                else:
                    self.set_float_height(0)
                self.snap_to_bottom()
            self._press_pos = None
        ev.accept()

    def _log(self, line: str) -> None:
        """调试：把事件写进 data/event.log，外面能看见到底进没进来。"""
        from pathlib import Path
        try:
            p = Path(__file__).resolve().parent / "data" / "event.log"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except Exception:
            pass

    def mouseDoubleClickEvent(self, ev) -> None:
        """双击：开输入框（而不是蹦一下）。"""
        self._last_dbl = time.monotonic()
        self._dragging = False
        self._grab = None
        self._press_pos = None
        self._log(f"dblclick button={ev.button()} hook={'有' if callable(self.on_double_click) else '没有'}")
        if ev.button() == Qt.LeftButton and callable(self.on_double_click):
            try:
                self.on_double_click()
                self._log("dblclick 回调跑完了")
            except Exception:
                import traceback
                self._log("dblclick 回调炸了: " + traceback.format_exc())
        ev.accept()

    def contextMenuEvent(self, ev) -> None:
        """右键：开对话页（双击要是不灵，就用这个）。"""
        self._log("rightclick")
        hook = self.on_right_click or self.on_double_click
        if callable(hook):
            hook()
        ev.accept()
