"""设置页：Coop 那样，左边一列，右边一张一张卡。

月下 13:00 说：「我觉得可以设置页，然后你也不要做的太单调了……你做好看一点，我们好有卖相。」

所以照着 Coop 的样子来（左边 logo + 分组导航，右边卡片），但配色用我们自己的
（底 `#f6f8fd`、卡白、强调蓝 `#4d7cfe`），字不挤、圆角大一点。

怎么开：右键身体 → 对话页右上角的齿轮；或者单独看 `python settings_page.py`。

改的东西直接写回 `config.json`（`memory.save_config`，顺手留一份 `config.backup.json`）。
"""
from __future__ import annotations

import datetime as _dt
import random
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame,
    QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizeGrip,
    QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

import alarms
import license as lic
import memory
import permissions as perm
import plug
import providers as prov
import usage
import voicepack
import update
from version import STAGE, VERSION

BG = "#f6f8fd"
SIDE = "#151f36"
CARD = "#ffffff"
SIDEINK = "#c9d5ec"
SIDEDIM = "#8798b8"
GLOW = "#46c8d8"
INK = "#1d2440"
SOFT = "#78839b"
ACCENT = "#4d7cfe"
LINE = "#e3e9f6"

STYLE = f"""
QWidget#root {{ background: transparent; }}
QWidget#body {{ background: transparent; }}
QFrame#shell {{ background: {BG}; border-radius: 16px; }}
QWidget#titlebar {{
    background: {SIDE};
    border-top-left-radius: 16px; border-top-right-radius: 16px;
}}
QLabel#tbname {{ color: #eaf1ff; font-size: 14px; font-weight: 700; }}
QLabel#tbsub {{ color: {SIDEDIM}; font-size: 10px; letter-spacing: 1.2px; }}
QPushButton#tbmin, QPushButton#tbclose, QPushButton#tbtoggle {{
    border: 0; background: transparent; color: #a7b5d2;
    font-size: 13px; border-radius: 8px;
}}
QPushButton#tbmin:hover, QPushButton#tbtoggle:hover {{ background: #22304d; color: #ffffff; }}
QPushButton#tbclose:hover {{ background: #ff5f57; color: #ffffff; }}
QWidget#side {{ background: {SIDE}; border-bottom-left-radius: 16px; }}
QWidget#side QLabel {{ color: {SIDEINK}; }}
QWidget#side QLabel#soft {{ color: {SIDEDIM}; }}
QPushButton#nav {{
    border: 0; background: transparent; color: {SIDEINK}; text-align: left;
    padding: 8px 12px; border-radius: 9px; font-size: 13px;
}}
QPushButton#nav:hover {{ background: #22304d; color: #ffffff; }}
QPushButton#nav:checked {{ background: {GLOW}; color: #10233c; font-weight: 600; }}
QFrame#content {{
    background: {CARD}; border: 0; border-bottom-right-radius: 16px;
}}
QPushButton#edge {{
    border: 0; background: rgba(70, 200, 216, 40); color: {SIDEDIM}; font-size: 10px;
    border-radius: 3px;
}}
QPushButton#edge:hover {{ background: {GLOW}; color: #10233c; }}
QFrame#card {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 14px;
}}
QFrame#xrow {{
    background: #fbfcff; border: 1px solid {LINE}; border-radius: 10px;
}}
QLabel#h1 {{ color: {INK}; font-size: 15px; font-weight: 600; }}
QLabel#h2 {{ color: {INK}; font-size: 13px; font-weight: 600; }}
QLabel#soft {{ color: {SOFT}; font-size: 12px; }}
QLabel#brand {{ color: {INK}; font-size: 19px; font-weight: 700; letter-spacing: 0.5px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #fbfcff; border: 1px solid {LINE}; border-radius: 9px;
    padding: 7px 10px; font-size: 13px; color: {INK};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ color: {INK}; font-size: 13px; spacing: 9px; }}
"""


def _card(title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
    """一张卡：标题 + 可选小字 + 竖排内容。"""
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 16, 18, 16)
    box.setSpacing(10)
    h = QLabel(title)
    h.setObjectName("h1")
    box.addWidget(h)
    if hint:
        s = QLabel(hint)
        s.setObjectName("soft")
        s.setWordWrap(True)
        box.addWidget(s)
    return frame, box


def _field(label: str, widget: QWidget, hint: str = "") -> QWidget:
    """一行：左边小标题 + 下面控件（竖着排，窄窗口也好看）。"""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    tag = QLabel(label)
    tag.setObjectName("h2")
    lay.addWidget(tag)
    lay.addWidget(widget)
    if hint:
        tip = QLabel(hint)
        tip.setObjectName("soft")
        tip.setWordWrap(True)
        lay.addWidget(tip)
    return box


def _primary(text: str) -> QPushButton:
    """蓝底白字的那颗按钮。

    **必须把样式写在这颗按钮自己身上**：卡片里的滚动区给子控件铺了
    `QWidget{background:transparent}`，从祖先继承下来会盖掉背景，
    结果就剩白字浮在卡片上（13:05 第一次弹出来就是这个毛病）。
    控件自己的 setStyleSheet 优先级最高，写这儿才压得住。
    """
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{ACCENT};color:#ffffff;border:0;border-radius:9px;"
        "padding:8px 20px;font-size:13px;font-weight:600;}"
        "QPushButton:hover{background:#3d6df0;}"
        "QPushButton:pressed{background:#3257cf;}"
        "QPushButton:disabled{background:#b9c8ef;}"
    )
    return b


def _ghost(text: str) -> QPushButton:
    """浅蓝底的小按钮（次要动作）。同理，样式写在它自己身上。"""
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:#e9effc;color:#43507a;border:0;border-radius:9px;"
        "padding:7px 14px;font-size:13px;}"
        f"QPushButton:hover{{background:#dde7fb;color:{ACCENT};}}"
    )
    return b


def _indicator_png(checked: bool) -> str:
    """勾选框那颗小方块的底图（17px，正好是显示尺寸）。

    QSS 一旦给 `::indicator` 设了 background，Qt 就**不画那个勾**了——13:43 试出来
    是一块光秃秃的蓝。所以勾也得自己画进图里，再用 image: 交给它。
    图缓存在临时目录，下次开窗直接读，不用每次画。
    """
    folder = Path(tempfile.gettempdir()) / "homestead-ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("check-on.png" if checked else "check-off.png")
    if path.exists():
        return path.as_posix()

    pm = QPixmap(17, 17)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    box = QRectF(0.9, 0.9, 15.2, 15.2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT) if checked else QColor("#ffffff"))
    p.drawRoundedRect(box, 5.0, 5.0)
    edge = QPen(QColor("#ffffff") if checked else QColor("#c9d4ec"))
    edge.setWidthF(1.4)
    p.setPen(edge)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(box, 5.0, 5.0)
    if checked:
        tick = QPen(QColor("#ffffff"))
        tick.setWidthF(1.9)
        tick.setCapStyle(Qt.RoundCap)
        tick.setJoinStyle(Qt.RoundJoin)
        p.setPen(tick)
        hook = QPainterPath()
        hook.moveTo(4.6, 8.7)
        hook.lineTo(7.3, 11.3)
        hook.lineTo(12.4, 5.6)
        p.drawPath(hook)
    p.end()
    pm.save(str(path), "PNG")
    return path.as_posix()


def _check(text: str) -> QCheckBox:
    """勾选框。老规矩：样式写在自己身上。

    13:43 试过把 `QCheckBox::indicator` 写进全局 STYLE——窗口里只出来一个光秃秃的
    勾，方块底和蓝边都没了：滚动区那句 `QWidget{background:transparent}` 是从更近的
    祖先下来的，把全局那条盖掉了。所以这里再写一遍。
    """
    c = QCheckBox(text)
    c.setCursor(Qt.PointingHandCursor)
    on, off = _indicator_png(True), _indicator_png(False)
    c.setStyleSheet(
        f"QCheckBox{{color:{INK};font-size:13px;spacing:9px;padding:3px 0;}}"
        f"QCheckBox:hover{{color:{ACCENT};}}"
        f"QCheckBox:disabled{{color:#a9b3c6;}}"
        f"QCheckBox::indicator{{width:17px;height:17px;image:url({off});}}"
        f"QCheckBox::indicator:checked{{image:url({on});}}"
    )
    return c


def _has_cutout(pm: QPixmap) -> bool:
    """这张图是不是「抠过」的（背景透明）？

    PNG 带 alpha 通道不代表背景真的透明——我们自己的立绘就是 alpha 通道 + 白底，
    只看 `hasAlphaChannel()` 会把白底当透明，贴在深色台上就成了一块亮板子。
    所以看四角：有角是透的，才当它是抠图。
    """
    img = pm.toImage()
    if not img.hasAlphaChannel():
        return False
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return False
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    return any(img.pixelColor(x, y).alpha() < 240 for x, y in corners)


class _Stage(QWidget):
    """装扮页那个深色台子：一点渐变 + 一层星点 + 中间站着的小人。

    为什么自己画：直接把图塞进 QLabel 铺不出这种台子（Coop 那边也是一块深色
    带星点的背景），而且立绘有白底的时候贴在深色上会像一块贴纸——有 alpha 就
    让深色透过去，没有就垫一张白卡，看着才不脏。
    """

    def __init__(self, pix: QPixmap | None = None) -> None:
        super().__init__()
        self._pix = pix or QPixmap()
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_pixmap(self, pix: QPixmap) -> None:
        self._pix = pix
        self.update()

    def paintEvent(self, _ev) -> None:          # noqa: N802  Qt 的命名
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QPainterPath()
        body.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        p.setClipPath(body)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#0b1230"))
        grad.setColorAt(1.0, QColor("#1a2450"))
        p.fillPath(body, QBrush(grad))

        # 星点：固定种子，窗口拉动也不会闪来闪去
        rnd = random.Random(7)
        p.setPen(Qt.NoPen)
        for _ in range(90):
            x = rnd.uniform(0, max(1, self.width()))
            y = rnd.uniform(0, max(1, self.height()))
            p.setBrush(QColor(255, 255, 255, rnd.randint(16, 80)))
            r = rnd.uniform(0.7, 1.7)
            p.drawEllipse(QPointF(x, y), r, r)

        if self._pix.isNull():
            p.setPen(QColor("#7c89b4"))
            f = p.font()
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "（还没有立绘）")
            return

        target_h = min(self.height() - 34, 200)
        pm = self._pix.scaledToHeight(int(target_h), Qt.SmoothTransformation)
        x = (self.width() - pm.width()) / 2
        y = (self.height() - pm.height()) / 2 + 4
        if _has_cutout(pm):
            # 抠过底的图：直接站在台子上
            p.drawPixmap(int(x), int(y), pm)
            return
        # 白底图：当成一张立绘卡（圆角裁一下），比硬贴一块白板好看
        pad = 8
        card = QRectF(x - pad, y - pad, pm.width() + pad * 2, pm.height() + pad * 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 16, 40, 90))
        p.drawRoundedRect(card.adjusted(-3, -3, 3, 5), 16, 16)     # 一点影子
        p.setBrush(QColor(255, 255, 255, 242))
        p.drawRoundedRect(card, 14, 14)
        clip = QPainterPath()
        clip.addRoundedRect(card, 14, 14)
        p.save()
        p.setClipPath(clip)
        p.drawPixmap(int(x), int(y), pm)
        p.restore()


class _Thumb(QWidget):
    """一块能点的缩略选项（走动频率那种），选中的描一圈蓝边。"""

    def __init__(self, title: str, hint: str, on_pick, group: list) -> None:
        super().__init__()
        self.value = title
        self._on_pick = on_pick
        self._group = group
        self._on = False
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("thumb")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(74)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)
        self._t = QLabel(title)
        self._t.setObjectName("h2")
        self._h = QLabel(hint)
        self._h.setObjectName("soft")
        lay.addWidget(self._t)
        lay.addWidget(self._h)
        self._repaint()

    def set_on(self, on: bool) -> None:
        self._on = on
        self._repaint()

    def _repaint(self) -> None:
        if self._on:
            self.setStyleSheet(
                f"_Thumb{{background:#eff4ff;border:2px solid {ACCENT};border-radius:12px;}}")
        else:
            self.setStyleSheet(
                "_Thumb{background:#fbfcff;border:1px solid #e3e9f6;border-radius:12px;}"
                "_Thumb:hover{background:#f5f8ff;border-color:#c9d8f7;}")

    def mousePressEvent(self, _ev) -> None:     # noqa: N802
        for t in self._group:
            t.set_on(t is self)
        self._on_pick(self.value)


def _tr(key: str, **kw) -> str:
    """页面正文用：按当前语言取词（带 {占位符} 的也能填）。"""
    return __import__("i18n").t(key, **kw)


def _page_head(title_key: str, subtitle_key: str = "") -> QWidget:
    """每一页顶上那一行：大标题 + 一句说明（Coop 也是这么排的）。

    传的是词表 key，不是写死的字；切语言时 retranslate() 重新 setText。
    """
    i = __import__("i18n")
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    h = QLabel(i.t(title_key))
    h.setStyleSheet(f"color:{INK};font-size:19px;font-weight:700;")
    lay.addWidget(h)
    box._title_key = title_key
    box._title_label = h
    if subtitle_key:
        s = QLabel(i.t(subtitle_key))
        s.setObjectName("soft")
        s.setWordWrap(True)
        lay.addWidget(s)
        box._sub_key = subtitle_key
        box._sub_label = s
    return box


class _TitleBar(QWidget):
    """自己画的标题栏：左边图标 + 名字，右边最小化 / 关闭，中间空白处能拖窗。"""

    def __init__(self, win: QWidget) -> None:
        super().__init__()
        self._win = win
        self._drag: QPointF | None = None
        self.setObjectName("titlebar")
        # 11-01 14:25 月下：顶端那条是白的，「鲸屿」两个字和图标都看不见了。
        # 病根：QWidget 的子类默认不画样式表里的 background，得自己开 WA_StyledBackground，
        # 不然 QWidget#titlebar 那条深色底根本不生效，白底配白字就看不见了。
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(46)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 0, 10, 0)
        h.setSpacing(9)

        mark = QLabel()
        mark.setFixedSize(26, 26)
        mark.setAlignment(Qt.AlignCenter)
        # 20:18 换成「我们现在用的那张」（isla）——用哪张只在 appicon.py 里定。
        # 以前写死 yuyu.ico，缩到 26 像素像条金鱼，月下说不好看。
        import appicon
        pic = appicon.pixmap(26)
        if pic is not None:
            mark.setPixmap(pic)
        name = QLabel("鲸屿")
        name.setObjectName("tbname")
        sub = QLabel("WHALE ISLE")
        sub.setObjectName("tbsub")
        h.addWidget(mark)
        h.addWidget(name)
        h.addWidget(sub)
        h.addStretch(1)

        for text, slot, obj in (("—", win.showMinimized, "tbmin"),
                                ("✕", win.close, "tbclose")):
            b = QPushButton(text)
            b.setObjectName(obj)
            b.setFixedSize(32, 26)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            h.addWidget(b)

    def mousePressEvent(self, ev) -> None:      # noqa: N802  Qt 的命名
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition() - self._win.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:       # noqa: N802
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
                self._drag = ev.globalPosition() - self._win.frameGeometry().topLeft()
            self._win.move((ev.globalPosition() - self._drag).toPoint())
            ev.accept()

    def mouseReleaseEvent(self, _ev) -> None:   # noqa: N802
        self._drag = None

    def mouseDoubleClickEvent(self, _ev) -> None:  # noqa: N802
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()


class SettingsPage(QWidget):
    def __init__(self, cfg: dict | None = None, chat: QWidget | None = None,
                 on_quit=None) -> None:
        super().__init__()
        # 2026-11-27：开源版有人报「关不掉、只能任务管理器」。这里接一个退出回调，
        # 「关于」页底部就有真的「退出鲸屿」了。没接（旧调用方）就不显示那颗按钮。
        self.on_quit = on_quit
        self.cfg = dict(cfg if cfg is not None else memory.load_config())
        __import__("i18n").set_lang(self.cfg.get("language") or "zh")
        self.setWindowTitle("鲸屿 · " + __import__("i18n").t("settings.title"))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        import appicon
        self.setWindowIcon(appicon.icon())
        self.resize(920, 700)
        self.setObjectName("root")
        self.setStyleSheet(STYLE)

        # ---------------- 左边 ----------------
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(196)
        self.side = side
        self._side_open = True
        s = QVBoxLayout(side)
        s.setContentsMargins(14, 18, 14, 14)
        s.setSpacing(6)

        ver = QLabel(f"鲸屿 · {VERSION}\n{STAGE}")
        ver.setObjectName("soft")
        s.addWidget(ver)
        s.addSpacing(14)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self._nav_keys: list[str] = []
        self._nav_buttons: list[QPushButton] = []
        for i, key in enumerate(["chat", "start", "who", "habit", "look", "voice",
                                 "day", "plug", "perm", "mem", "diag", "about"]):
            b = QPushButton(__import__("i18n").t("nav." + key))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(b, i)
            s.addWidget(b)
            self._nav_keys.append(key)
            self._nav_buttons.append(b)
            if i == 1:                      # 默认停在「开始」，对话是里面的一页
                b.setChecked(True)
        s.addStretch(1)

        # 底下那条：小小的立绘 + 名字 + 在不在（Coop 左栏底部也是这么一块）
        who = QWidget()
        wl = QHBoxLayout(who)
        wl.setContentsMargins(2, 0, 0, 0)
        wl.setSpacing(8)
        av = QLabel()
        av.setFixedSize(34, 34)
        av.setAlignment(Qt.AlignCenter)
        av.setStyleSheet("QLabel{background:#ffffff;border-radius:9px;}")
        img = str(self.cfg.get("figure_image", "") or "")
        pix = QPixmap(img) if img and Path(img).exists() else QPixmap()
        if not pix.isNull():
            av.setPixmap(pix.scaledToHeight(30, Qt.SmoothTransformation))
        else:
            av.setText("·")
        info = QVBoxLayout()
        info.setSpacing(0)
        nm = QLabel(str(self.cfg.get("name", "新朋友")))
        nm.setStyleSheet(f"color:{SIDEINK};font-size:12px;font-weight:600;")
        st = QLabel("● 在底边上")
        st.setStyleSheet("color:#3ec27a;font-size:10px;")
        info.addWidget(nm)
        info.addWidget(st)
        wl.addWidget(av)
        wl.addLayout(info, 1)
        s.addWidget(who)

        self.saved = QLabel("")
        self.saved.setObjectName("soft")
        self.saved.setWordWrap(True)
        s.addWidget(self.saved)

        # 界面语言：中文 / English。切了当场换导航和页标题，写进 config 下次还记得。
        lang_row = QHBoxLayout()
        lang_row.setSpacing(6)
        for code in ("zh", "en"):
            lb = QPushButton(__import__("i18n").t("lang." + code))
            lb.setCursor(Qt.PointingHandCursor)
            lb.clicked.connect(lambda _=False, c=code: self.set_language(c))
            lang_row.addWidget(lb)
        s.addLayout(lang_row)

        # ---------------- 右边 ----------------
        self.stack = QStackedWidget()
        # 11-01 14:05 月下：「把对话加到设置里头」——所以对话是这里的第一页，
        # 双击打开软件先站出来的是「设置」，不再是单独一个对话窗。
        self.chat = chat if chat is not None else self._make_chat()
        self.stack.addWidget(self.chat)
        self.stack.addWidget(self._page_start())
        self.stack.addWidget(self._page_who())
        self.stack.addWidget(self._page_habit())
        self.stack.addWidget(self._page_look())
        self.stack.addWidget(self._page_voice())
        self.stack.addWidget(self._page_day())
        self.stack.addWidget(self._page_plug())
        self.stack.addWidget(self._page_perm())
        self.stack.addWidget(self._page_mem())
        self.stack.addWidget(self._page_diag())
        self.stack.addWidget(self._page_about())
        self.nav.idClicked.connect(self.stack.setCurrentIndex)
        self.stack.setCurrentIndex(1)        # 开场站「开始」页，不站对话页
        # 11-21 18:2x：只动 stack 不动按钮组，开机就会「导航亮着对话、内容却是开始页」
        # （他录的视频里就是这个状态）。补一句把按钮也摁到同一格。
        _b = self.nav.button(1)
        if _b is not None:
            _b.setChecked(True)

        body = QWidget()
        body.setObjectName("body")
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(side)

        # 内容包一层浅色框（19:52 月下：「内容做浅，四周框」）
        self.panel = QFrame()
        self.panel.setObjectName("content")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(self.stack)
        # 不画任何框：白底直接贴到窗口边，靠深色左栏的颜色差分开就够了。
        # （19:57 月下：「不，我的意思是把整个边框都删了。框还是有点太丑了。」）
        root.addWidget(self.panel, 1)

        # 收 / 放的那条把手：body 的子控件，自己摆位置。
        # 19:53 月下：「把那个收放功能挪到这边的最侧面，点一下就能收放。」
        # 19:56 踩过：塞进 QHBoxLayout 会被压成一小块方钮挂在中腰，点不中。
        self.body = body
        self.edge = QPushButton("", body)
        self.edge.setObjectName("edge")
        self.edge.setCursor(Qt.PointingHandCursor)
        self.edge.setToolTip("点一下收起 / 展开左边的选栏")
        self.edge.clicked.connect(self.toggle_side)
        self.edge.setFixedWidth(9)
        self.edge.raise_()

        # 自己画的一条标题栏：系统那条只肯放 16 像素图标一行字，看着像对话框
        shell = QFrame()
        shell.setObjectName("shell")
        sl = QVBoxLayout(shell)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(_TitleBar(self))
        sl.addWidget(body, 1)

        # 11-21 18:2x：投影特效撤了。
        # 他要的是「少闪」，而这层特效让 Qt 把整个窗口子树画进一张离屏图再合成；
        # 窗口本身是 WA_TranslucentBackground，合成一次没填满就露一次底色 ——
        # 每次重绘露一下，开机那一下连着露十几次，就是他在视频里看到的那块淡卡片。
        # 不用 QGraphicsDropShadowEffect 了，改成 shell 自己 paintEvent 画的那圈软边（见下）。

        outer = QVBoxLayout(self)
        # 11-01 14:22 月下：外面那圈白边太突兀（截图里红线标的就是它）——不留边距，
        # 让壳直接贴到窗口边，白边和四角的空档一起消掉。
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(shell)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)
        self._grip.setStyleSheet("QSizeGrip{background:transparent;border:0;}")
        self._grip.raise_()
        QTimer.singleShot(0, self._place_edge)   # 布局算完再摆那块把手

    def _make_chat(self) -> QWidget:
        """自己造一张对话页（main.py 没传进来的时候用）。"""
        from page import ChatPage
        return ChatPage(self.cfg, lambda *a, **k: None, embedded=True)

    def go_chat(self) -> None:
        """跳到「对话」那一页（右键身体、或者从别处叫过来时用）。"""
        btn = self.nav.button(0)
        if btn is not None:
            btn.setChecked(True)
        self.stack.setCurrentIndex(0)

    def retranslate(self) -> None:
        """按当前语言重刷页面层：导航 + 每页标题/说明 + 窗口标题。正文还没铺。"""
        i = __import__("i18n")
        self.setWindowTitle("鲸屿 · " + i.t("settings.title"))
        for key, btn in zip(self._nav_keys, self._nav_buttons):
            btn.setText(i.t("nav." + key))
        for idx in range(self.stack.count()):
            w = self.stack.widget(idx)
            if w is None:
                continue
            for box in w.findChildren(QWidget):
                key = getattr(box, "_title_key", None)
                if key and getattr(box, "_title_label", None) is not None:
                    box._title_label.setText(i.t(key))
                sub = getattr(box, "_sub_key", None)
                if sub and getattr(box, "_sub_label", None) is not None:
                    box._sub_label.setText(i.t(sub))

    def _rebuild_translated(self) -> None:
        """正文已铺好词表的页，切语言时就地重建（开始 = 1、习惯 = 3）。

        别的页正文还是写死中文，重建也没用，等按页铺完再一页页加进来。
        """
        idx = self.stack.currentIndex()
        for i, factory in ((1, self._page_start), (3, self._page_habit),
                           (5, self._page_voice), (8, self._page_perm),
                           (11, self._page_about)):
            old = self.stack.widget(i)
            timer = getattr(old, "_vp_timer", None)
            if timer is not None:
                timer.stop()
            new = factory()
            self.stack.insertWidget(i, new)
            self.stack.removeWidget(old)
            old.deleteLater()
        self.stack.setCurrentIndex(idx)

    def set_language(self, code: str) -> None:
        """切界面语言：当场刷导航/页标题，写进 config，下次开机还是它。"""
        import i18n
        i18n.set_lang("en" if str(code).lower().startswith("en") else "zh")
        try:
            import memory
            memory.update_config(language=i18n.lang())
        except Exception:                        # noqa: BLE001
            pass
        self.retranslate()
        try:
            self._rebuild_translated()           # 开始/习惯正文立刻换；别的页等重启
        except Exception:                        # noqa: BLE001
            pass
        self.saved.setText(i18n.t("lang.saved"))

    def resizeEvent(self, ev) -> None:          # noqa: N802  Qt 的命名
        super().resizeEvent(ev)
        if hasattr(self, "_grip"):
            self._grip.move(self.width() - 16, self.height() - 18)
        self._place_edge()

    def _place_edge(self) -> None:
        """把手贴在左栏的右边那一条；收起之后贴着窗口最左边。"""
        edge = getattr(self, "edge", None)
        body = getattr(self, "body", None)
        if edge is None or body is None:
            return
        if self.side.isVisible():
            g = self.side.geometry()
            edge.setGeometry(g.right() - 4, g.top() + 8, 9, max(28, g.height() - 16))
            edge.setText("‹")
        else:
            edge.setGeometry(6, 14, 9, max(28, body.height() - 28))
            edge.setText("›")
        edge.raise_()

    def toggle_side(self) -> None:
        """左栏收 / 放。19:52 月下：「旁边的选栏做一个可以收、可以放的东西。」"""
        self._side_open = not getattr(self, "_side_open", True)
        self.side.setVisible(self._side_open)
        QTimer.singleShot(0, self._place_edge)

    # ---------------- 小工具 ----------------
    def _scroll(self, *cards: QWidget) -> QWidget:
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(14)
        for c in cards:
            box.addWidget(c)
        box.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(holder)
        area.setStyleSheet(
            f"QScrollArea{{background:{CARD};border:0;border-bottom-right-radius:12px;}}"
            " QWidget{background:transparent;}"
        )
        return area

    def _save(self, note: str = "存好了") -> None:
        try:
            memory.save_config(self.cfg)
            self.saved.setText(f"✓ {note}")
        except OSError as exc:
            self.saved.setText(f"存不下来：{exc}")
            return
        # 5-2：存完推一条「什么变了」给下一轮模型；改不动的写「要重启」。
        try:
            import json as _json
            old: dict = {}
            try:
                old = _json.loads((memory.HOME / "config.backup.json").read_text(encoding="utf-8"))
            except Exception:                    # noqa: BLE001
                old = {}
            changed = memory.config_diff(old, self.cfg)
            note = memory.config_note(changed)
            if note:
                import hooks
                hooks.HOOKS.push(note, source="设置")
        except Exception:                        # noqa: BLE001
            pass
        # 11-04 17:39 月下：「改成保存一下就能正常使用，不用重启。」
        # 所以每存一次都通知外面一遍，能当场换的当场换。
        cb = getattr(self, "on_apply", None)
        if callable(cb):
            try:
                cb(self.cfg)
            except Exception as exc:              # noqa: BLE001
                self.saved.setText(f"✓ {note}（有一项没当场换上：{exc}）")

    # ---------------- 开始：模型 ----------------
    def _page_start(self) -> QWidget:
        card, box = _card(_tr("page.start.model.title"), _tr("page.start.model.sub"))

        self.model = QLineEdit(str(self.cfg.get("api_model", "deepseek-chat")))
        self.model.setPlaceholderText("deepseek-chat / qwen-plus / glm-4-flash …")
        self.base = QLineEdit(str(self.cfg.get("api_base", "https://api.deepseek.com/v1")))
        self.key = QLineEdit(str(self.cfg.get("api_key", "")))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText(_tr("page.start.key.placeholder"))

        # 一排小胶囊挑家：别家也得能用（月下 19:19 提的）。
        # 不用 QComboBox——透明窗口里它的弹层是块黑，见「权限」那页同一个坑。
        pick = QWidget()
        pv = QVBoxLayout(pick)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(6)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.prov_group = QButtonGroup(pick)
        self.prov_group.setExclusive(True)
        self.prov_buttons: dict[str, QPushButton] = {}
        cur = prov.guess_id(self.base.text(), self.model.text())
        for i, (pid, name, url, _models, _note) in enumerate(prov.PROVIDERS):
            b = QPushButton(_tr(f"page.start.provider.{pid}.name"))
            b.setCheckable(True)
            b.setChecked(pid == cur)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, p=pid: self._pick_provider(p))
            self.prov_group.addButton(b)
            self.prov_buttons[pid] = b
            grid.addWidget(b, i // 3, i % 3)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        grid_w.setStyleSheet(
            f"QPushButton{{border:1px solid {LINE};background:#ffffff;color:{INK};"
            "border-radius:8px;padding:6px 8px;font-size:12px;}"
            f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
            f"QPushButton:checked{{background:{ACCENT};border-color:{ACCENT};"
            "color:#ffffff;font-weight:600;}"
        )
        pv.addWidget(grid_w)

        self.prov_note = QLabel(_tr(f"page.start.provider.{cur}.note"))
        self.prov_note.setObjectName("soft")
        self.prov_note.setWordWrap(True)
        pv.addWidget(self.prov_note)
        box.addWidget(_field(_tr("page.start.provider.label"), pick,
                             _tr("page.start.provider.hint")))

        box.addWidget(_field(_tr("page.start.model.label"), self.model))
        box.addWidget(_field(_tr("page.start.base.label"), self.base,
                             _tr("page.start.base.hint")))
        box.addWidget(_field("API Key", self.key, _tr("page.start.key.hint")))

        row = QHBoxLayout()
        test = _ghost(_tr("page.start.test"))
        test.clicked.connect(self._test_model)
        row.addWidget(test)
        self.test_note = QLabel("")
        self.test_note.setObjectName("soft")
        self.test_note.setWordWrap(True)
        row.addWidget(self.test_note, 1)
        save = _primary(_tr("page.start.save_start"))
        save.clicked.connect(self._save_model)
        row.addWidget(save)
        box.addLayout(row)

        # 19:38 月下：「用一串代码藏到开始页吧，让一开始就有人能发现这些小秘密。」
        # 这串十六进制按 UTF-8 解出来是一句给他看的话——谜底不写在这里，
        # 只记在咱俩自己的笔记里（`彩蛋-十处.md` 在工作区，不进包）。
        # 跟关于页那行 base64 是一对：换种码，才让人愿意多找几处。
        egg = QLabel("ncjZk+TQnc//msX5nNv6kMnEn+nwkNfDnc//")
        egg.setStyleSheet("color:#e9effc;font-size:8px;letter-spacing:1px;")
        egg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(egg)

        heart, hb = _card(_tr("page.start.heart.title"), _tr("page.start.heart.sub"))
        self.hb = QSpinBox()
        self.hb.setRange(1, 240)
        self.hb.setSuffix(_tr("page.start.minutes"))
        self.hb.setValue(int(self.cfg.get("heartbeat_minutes", 30) or 30))
        hb.addWidget(_field(_tr("page.start.heart.label"), self.hb, _tr("page.start.heart.hint")))
        hb_row = QHBoxLayout()
        hb_row.addStretch(1)
        hb_save = _ghost(_tr("page.start.save"))
        hb_save.clicked.connect(lambda: self._save(_tr("page.start.saved_heart")))
        hb_row.addWidget(hb_save)
        hb.addLayout(hb_row)

        return self._scroll(_page_head("page.start.title", "page.start.sub"), card, heart)

    def _pick_provider(self, pid: str) -> None:
        """挑了一家：地址和模型名换成这家的，小字也跟着换。"""
        _pid, _name, url, models, note = prov.BY_ID[pid]
        if url:
            self.base.setText(url)
        if models:
            self.model.setText(models[0])
        self.prov_note.setText(_tr(f"page.start.provider.{pid}.note"))

    def _test_model(self) -> None:
        """拿现在这几个框里的东西真发一句话，通不通立刻说。

        直接在这儿同步发（最多等 20 秒），就为了点完马上有话说；
        真接上以后这颗按钮也该换成后台线程，别卡窗口。
        """
        import llm

        cfg = dict(self.cfg)
        cfg["api_base"] = self.base.text().strip() or "https://api.deepseek.com/v1"
        cfg["api_model"] = self.model.text().strip() or "deepseek-chat"
        key = self.key.text().strip()
        if key:
            cfg["api_key"] = key
        self.test_note.setText(_tr("page.start.testing"))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            out = llm.chat([{"role": "user", "content": "只回两个字：在的"}], cfg, timeout=20.0)
        finally:
            QApplication.restoreOverrideCursor()
        ok = out and not out.startswith("（脑子出错了")
        self.test_note.setText((_tr("page.start.test.ok") if ok else "× ") + out[:60])

    def _save_model(self) -> None:
        self.cfg["api_model"] = self.model.text().strip() or "deepseek-chat"
        self.cfg["api_base"] = self.base.text().strip() or "https://api.deepseek.com/v1"
        key = self.key.text().strip()
        if key:
            self.cfg["api_key"] = key
        self._save(_tr("page.start.saved"))

    # ---------------- 个性 ----------------
    def _egg_card(self, code: str) -> QWidget:
        """彩蛋：一行看得见又看不清的小字，垫在页面最底下。

        月下 19:39：「一共藏个十处吧」「把谜底和答案发我一份」。
        一页一处，码法各不相同（hex / base64 / base32 / \\u 转义 / 倒着写）——
        十处全找到了，才知道翻到哪儿算完。
        """
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 0, 6, 8)
        lab = QLabel(code)
        lab.setStyleSheet("color:#e9effc;font-size:8px;letter-spacing:1px;")
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(lab)
        v.addStretch(1)
        return w

    def _page_who(self) -> QWidget:
        card, box = _card("他是谁",
                          "名字会出现在气泡、对话页和网页标题上。")
        self.name = QLineEdit(str(self.cfg.get("name", "新朋友")))
        box.addWidget(_field("名字", self.name))

        self.user_name = QLineEdit(str(self.cfg.get("user_name", "")))
        self.user_name.setPlaceholderText("老爹 / 主人 / 你的名字…")
        box.addWidget(_field("它怎么称呼对方", self.user_name))

        row = QHBoxLayout()
        row.addStretch(1)
        save = _primary("保存")
        save.clicked.connect(self._save_who)
        row.addWidget(save)
        box.addLayout(row)

        mind, mb = _card("系统提示词",
                         "人格 = 工作区里这三份纯文本。写它，比在设置里点勾更管用。")
        ws = memory.workspace(self.cfg)
        for fname in ("CONSTITUTION.md", "PARTNER.md", "STATE.md"):
            p = ws / fname
            line = QLabel(f"{fname} · {'有' if p.exists() else '还没有'}")
            line.setObjectName("soft")
            mb.addWidget(line)
        open_btn = _ghost("打开工作区")
        open_btn.clicked.connect(lambda: self._open(ws))
        mb.addWidget(open_btn, 0, Qt.AlignRight)

        return self._scroll(_page_head("page.who.title", "page.who.sub"), card, mind,
                            self._egg_card("kcrgkMXVns/Bk+Han/3onf7fnMLIkP/snu/9"))

    def _save_who(self) -> None:
        """个性页的保存：把名字和称呼真正写进 cfg。

        2026-11-02 修：原来这里直接接 `self._save`，输入框里的字一个都没进 cfg，
        点「保存」也提示成功，重启就回到旧值——测试版用户（平凡）报的就是这个。
        """
        self.cfg["name"] = self.name.text().strip() or "新朋友"
        self.cfg["user_name"] = self.user_name.text().strip()
        self._save("名字存好了，重启后生效")

    def _open(self, path: Path) -> None:
        import os
        try:
            os.startfile(str(path))          # noqa: S606  Windows 上就这么开文件夹
        except Exception as exc:             # noqa: BLE001
            self.saved.setText(f"打不开：{exc}")

    # ---------------- 装扮 ----------------
    def _page_look(self) -> QWidget:
        stage, sb = _card("它站在屏幕上的样子")
        self.preview = _Stage()
        self._refresh_preview()
        sb.addWidget(self.preview)
        hint = QLabel("换形象要放一张立绘进 config.json 的 figure_image。")
        hint.setObjectName("soft")
        sb.addWidget(hint)

        move, mb = _card("走动", "在屏幕底边上自己溜达多少。")
        self._roam_value = str(self.cfg.get("roam", "free") or "free")
        self._roam_thumbs: list[_Thumb] = []
        roam_row = QHBoxLayout()
        roam_row.setSpacing(10)
        for key, title, hint in [("free", "经常走", "隔一会儿就溜达一圈"),
                                 ("calm", "基本站着", "被叫的时候才动"),
                                 ("off", "不动", "一直站在底边")]:
            t = _Thumb(title, hint, self._pick_roam, self._roam_thumbs)
            t.value = key
            self._roam_thumbs.append(t)
            roam_row.addWidget(t)
        for t in self._roam_thumbs:
            t.set_on(t.value == self._roam_value)
        roam_holder = QWidget()
        roam_holder.setLayout(roam_row)
        mb.addWidget(_field("走动的频率", roam_holder))

        self.speak = _check("说话时出声")
        self.speak.setChecked(bool(self.cfg.get("speak_aloud", True)))
        mb.addWidget(self.speak)

        self.figure_on = _check("站在屏幕上")
        self.figure_on.setChecked(bool(self.cfg.get("figure_visible", True)))
        mb.addWidget(self.figure_on)
        mb.addWidget(QLabel("关掉之后屏幕上不留人，只剩任务栏那一格——点它开设置和对话页。"))

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.5, 3.0)
        self.scale.setSingleStep(0.1)
        self.scale.setValue(float(self.cfg.get("scale", 1.0) or 1.0))
        mb.addWidget(_field("大小", self.scale, "1.0 是原尺寸。"))

        self.float_h = QSpinBox()
        self.float_h.setRange(0, 600)
        self.float_h.setSingleStep(10)
        self.float_h.setSuffix(" px")
        self.float_h.setValue(int(self.cfg.get("float_height", 0) or 0))
        mb.addWidget(_field("离地高度", self.float_h,
                            "0 = 贴着底边站。也可以直接把她拎起来松手，她就悬在那儿（鼠标靠近会沉下来凑近）。"))

        row = QHBoxLayout()
        row.addStretch(1)
        save = _primary("保存")
        save.clicked.connect(self._save_look)
        row.addWidget(save)
        mb.addLayout(row)

        return self._scroll(_page_head("page.look.title", "page.look.sub"), stage, move,
                            self._egg_card("n/jbndjWn+n0kcH4ntvuk/TXnc/D"))

    def _refresh_preview(self) -> None:
        img = str(self.cfg.get("figure_image", "") or "")
        pix = QPixmap(img) if img and Path(img).exists() else QPixmap()
        self.preview.set_pixmap(pix)

    def _pick_roam(self, key: str) -> None:
        self._roam_value = key

    def _save_look(self) -> None:
        self.cfg["roam"] = self._roam_value
        self.cfg["speak_aloud"] = self.speak.isChecked()
        self.cfg["figure_visible"] = self.figure_on.isChecked()
        self.cfg["scale"] = round(float(self.scale.value()), 2)
        self.cfg["float_height"] = int(self.float_h.value())
        self._save("装扮存好了")

    # ---------------- 习惯 ----------------
    def _page_habit(self) -> QWidget:
        """习惯：她多久动一次、一次想几步、气泡长什么样。

        照 Coop 的「习惯」页搬的，只搬我这儿真接得上的那几项（见 计划-对标Coop页面表.md）。
        """
        rhythm, rb = _card(_tr("page.habit.rhythm.title"), _tr("page.habit.rhythm.sub"))
        self.habit_beat = QSpinBox()
        self.habit_beat.setRange(1, 240)
        self.habit_beat.setSuffix(_tr("page.habit.minutes"))
        self.habit_beat.setValue(int(self.cfg.get("heartbeat_minutes", 5) or 5))
        rb.addWidget(_field(_tr("page.habit.beat.label"), self.habit_beat,
                            _tr("page.habit.beat.hint")))

        self.habit_steps = QSpinBox()
        self.habit_steps.setRange(1, 20)
        self.habit_steps.setSuffix(_tr("page.habit.steps"))
        self.habit_steps.setValue(int(self.cfg.get("max_steps", 6) or 6))
        rb.addWidget(_field(_tr("page.habit.steps.label"), self.habit_steps,
                            _tr("page.habit.steps.hint")))

        self.habit_fs = _check(_tr("page.habit.fullscreen"))
        self.habit_fs.setChecked(bool(self.cfg.get("hide_fullscreen", False)))
        rb.addWidget(self.habit_fs)
        fs_hint = QLabel(_tr("page.habit.fullscreen.hint"))
        fs_hint.setObjectName("soft")
        fs_hint.setWordWrap(True)
        rb.addWidget(fs_hint)

        bubble, bb = _card(_tr("page.habit.bubble.title"), _tr("page.habit.bubble.sub"))
        self.habit_font = QSpinBox()
        self.habit_font.setRange(70, 200)
        self.habit_font.setSuffix(" %")
        self.habit_font.setValue(int(round(float(self.cfg.get("bubble_font", 1.0) or 1.0) * 100)))
        bb.addWidget(_field(_tr("page.habit.font.label"), self.habit_font, _tr("page.habit.font.hint")))

        self.habit_width = QSpinBox()
        self.habit_width.setRange(60, 160)
        self.habit_width.setSuffix(" %")
        self.habit_width.setValue(int(round(float(self.cfg.get("bubble_width", 1.0) or 1.0) * 100)))
        bb.addWidget(_field(_tr("page.habit.width.label"), self.habit_width, _tr("page.habit.width.hint")))

        self.habit_secs = QDoubleSpinBox()
        self.habit_secs.setRange(1.0, 30.0)
        self.habit_secs.setSingleStep(0.5)
        self.habit_secs.setSuffix(_tr("page.habit.secs.suffix"))
        self.habit_secs.setValue(float(self.cfg.get("bubble_seconds", 5.0) or 5.0))
        bb.addWidget(_field(_tr("page.habit.secs.label"), self.habit_secs,
                            _tr("page.habit.secs.hint")))

        row = QHBoxLayout()
        row.addStretch(1)
        save = _primary(_tr("page.habit.save"))
        save.clicked.connect(self._save_habit)
        row.addWidget(save)
        bb.addLayout(row)

        # ---- 开机时（15:14 月下要的：开场动画得能关）----
        # cfg["boot_animation"] 一直存在（start / daily / off），只是设置页里没有 UI，
        # 等于关不掉。判断只有 boot.decide_play 一处，这里只负责写进 cfg。
        bootc, bo = _card(_tr("page.habit.boot.title"), _tr("page.habit.boot.sub"))
        pick = QWidget()
        pv = QVBoxLayout(pick)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(6)

        grid_w = QWidget()
        grid = QHBoxLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.boot_group = QButtonGroup(pick)
        self.boot_group.setExclusive(True)
        self.boot_buttons: dict[str, QPushButton] = {}
        cur_mode = str(self.cfg.get("boot_animation", "start")).strip().lower()
        if cur_mode not in ("start", "daily", "off"):
            cur_mode = "start"
        for mode, name in (("start", _tr("page.habit.boot.start")),
                           ("daily", _tr("page.habit.boot.daily")),
                           ("off", _tr("page.habit.boot.off"))):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(mode == cur_mode)
            b.setCursor(Qt.PointingHandCursor)
            self.boot_group.addButton(b)
            self.boot_buttons[mode] = b
            grid.addWidget(b, 1)
        grid_w.setStyleSheet(
            f"QPushButton{{border:1px solid {LINE};background:#ffffff;color:{INK};"
            "border-radius:8px;padding:6px 8px;font-size:12px;}"
            f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
            f"QPushButton:checked{{background:{ACCENT};border-color:{ACCENT};"
            "color:#ffffff;font-weight:600;}"
        )
        pv.addWidget(grid_w)
        bo.addWidget(_field(_tr("page.habit.boot.label"), pick, _tr("page.habit.boot.hint")))

        self.habit_greet = _check(_tr("page.habit.greet"))
        self.habit_greet.setChecked(bool(self.cfg.get("greet_on_start", True)))
        bo.addWidget(self.habit_greet)
        greet_hint = QLabel(_tr("page.habit.greet.hint"))
        greet_hint.setObjectName("soft")
        greet_hint.setWordWrap(True)
        bo.addWidget(greet_hint)

        rowb = QHBoxLayout()
        rowb.addStretch(1)
        saveb = _primary(_tr("page.habit.save"))
        saveb.clicked.connect(self._save_boot)
        rowb.addWidget(saveb)
        bo.addLayout(rowb)

        return self._scroll(_page_head("page.habit.title", "page.habit.sub"),
                            rhythm, bubble, bootc)

    def _save_boot(self) -> None:
        mode = "start"
        for key, btn in getattr(self, "boot_buttons", {}).items():
            if btn.isChecked():
                mode = key
                break
        self.cfg["boot_animation"] = mode
        self.cfg["greet_on_start"] = bool(self.habit_greet.isChecked())
        self._save(_tr("page.habit.boot.saved"))

    def _save_habit(self) -> None:
        self.cfg["heartbeat_minutes"] = int(self.habit_beat.value())
        self.cfg["max_steps"] = int(self.habit_steps.value())
        self.cfg["bubble_font"] = round(float(self.habit_font.value()) / 100.0, 2)
        self.cfg["bubble_width"] = round(float(self.habit_width.value()) / 100.0, 2)
        self.cfg["bubble_seconds"] = round(float(self.habit_secs.value()), 1)
        self.cfg["hide_fullscreen"] = self.habit_fs.isChecked()
        self._save(_tr("page.habit.saved"))

    # ---------------- 声音 ----------------
    def _page_voice(self) -> QWidget:
        card, box = _card(_tr("page.sound.input.title"), _tr("page.sound.input.sub"))
        self.ears = _check(_tr("page.sound.ears"))
        self.ears.setChecked(bool(self.cfg.get("ears", False)))
        box.addWidget(self.ears)

        self.ear_key = QLineEdit(str(self.cfg.get("ear_key", "f9")))
        box.addWidget(_field(_tr("page.sound.key.label"), self.ear_key, _tr("page.sound.key.hint")))

        # ---- 选具体的麦克风（11-06 照 Coop 0.2.18 那条搬过来的）----
        # 以前只能让系统挑默认：一插耳机、一开会，声音就不知道跑哪去了。
        # 这里不用 QComboBox —— 透明窗口里它的弹层是块黑（见下面权限页那段注释）。
        self.mic_choice = str(self.cfg.get("mic_device", "") or "")
        box.addWidget(self._mic_picker())

        self.asr = QLineEdit(str(self.cfg.get("asr_url", "")))
        self.asr.setPlaceholderText("http://127.0.0.1:8100/asr")
        box.addWidget(_field(_tr("page.sound.asr.label"), self.asr, _tr("page.sound.asr.hint")))

        # ---- 本地识别模型（语音包）----
        # 月下 11-01 14:54：「把 Coop 这个语音包的下载链接贴到里头，让他自己选择要不要下，
        # 下的话我们就本地帮他下。」所以：先摆出多大、从哪儿下，人点了才动。
        vp = voicepack.status()
        self._vp_job = None            # 下载线程（一次只跑一个）
        self._vp_now = {"done": 0, "total": 1, "msg": "", "running": False}
        self._vp_timer = QTimer(self)
        self._vp_timer.timeout.connect(self._vp_tick)
        self.vp_status = QLabel(self._vp_line(vp))
        self.vp_status.setStyleSheet("font-weight:600;")
        box.addWidget(self.vp_status)

        self.vp_bar = QProgressBar()
        self.vp_bar.setRange(0, 1000)
        self.vp_bar.setTextVisible(False)
        self.vp_bar.setFixedHeight(8)
        self.vp_bar.setVisible(False)
        box.addWidget(self.vp_bar)

        vp_row = QHBoxLayout()
        self.vp_dl = _primary(_tr("page.sound.pack.download", mb=vp["mb"])
                              if vp["phase"] != "ready"
                              else _tr("page.sound.pack.redownload"))
        self.vp_dl.clicked.connect(self._vp_install)
        vp_row.addWidget(self.vp_dl)
        self.vp_del = _ghost(_tr("page.sound.pack.delete"))
        self.vp_del.clicked.connect(self._vp_delete)
        vp_row.addWidget(self.vp_del)
        vp_row.addStretch(1)
        box.addLayout(vp_row)

        link = voicepack.SOURCES[0]("model.int8.onnx")
        self.vp_link = QLabel(_tr("page.sound.pack.source",
                                  link=link.replace('model.int8.onnx', '…')))
        self.vp_link.setWordWrap(True)
        self.vp_link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.vp_link.setStyleSheet("color:#7b8aa6;font-size:11px;")
        box.addWidget(self.vp_link)

        self.vp_hint = QLabel(_tr("page.sound.pack.hint"))
        self.vp_hint.setWordWrap(True)
        self.vp_hint.setStyleSheet("color:#7b8aa6;font-size:12px;")
        box.addWidget(self.vp_hint)

        row = QHBoxLayout()
        row.addStretch(1)
        save = _primary(_tr("page.sound.save"))
        save.clicked.connect(self._save_voice)
        row.addWidget(save)
        box.addLayout(row)

        mouth, mb = _card(_tr("page.sound.output.title"), _tr("page.sound.output.sub"))
        self.voice_name = QLineEdit(str(self.cfg.get("tts_voice", "")))
        self.voice_name.setPlaceholderText(_tr("page.sound.voice.placeholder"))
        mb.addWidget(_field(_tr("page.sound.voice.label"), self.voice_name))
        self.tts_url = QLineEdit(str(self.cfg.get("tts_url", "")))
        self.tts_url.setPlaceholderText("http://127.0.0.1:9880/tts")
        mb.addWidget(_field(_tr("page.sound.tts.label"), self.tts_url))
        row2 = QHBoxLayout()
        row2.addStretch(1)
        save2 = _primary(_tr("page.sound.save"))
        save2.clicked.connect(self._save_voice)
        row2.addWidget(save2)
        mb.addLayout(row2)

        return self._scroll(_page_head("page.voice.title", "page.voice.sub"), card, mouth,
                            self._egg_card("nOHIkcH4nc3zkPfOnczmkcH4kc/L"))

    # ---- 语音包：下 / 删 / 进度 ----
    @staticmethod
    def _vp_line(vp: dict) -> str:
        if vp["phase"] == "ready":
            return _tr("page.sound.pack.ready")
        if vp["phase"] == "partial":
            return _tr("page.sound.pack.partial", done=f"{vp['done'] / 1048576:.0f}", mb=vp["mb"])
        return _tr("page.sound.pack.none", mb=vp["mb"])

    def _vp_install(self) -> None:
        if self._vp_job is not None and self._vp_job.is_alive():
            return
        import threading

        self._vp_now = {"done": 0, "total": voicepack.TOTAL, "msg": "", "running": True}
        self.vp_dl.setEnabled(False)
        self.vp_bar.setVisible(True)
        self.vp_bar.setValue(0)
        self.vp_status.setText(_tr("page.sound.pack.downloading"))
        self.vp_hint.setText(_tr("page.sound.pack.bg"))

        def progress(_name: str, done: int, total: int) -> None:
            self._vp_now["done"] = done
            self._vp_now["total"] = max(1, total)

        def work() -> None:
            try:
                voicepack.install(progress)
                self._vp_now["msg"] = _tr("page.sound.pack.done")
            except Exception as exc:                       # noqa: BLE001
                self._vp_now["msg"] = _tr("page.sound.pack.failed", exc=exc)
            self._vp_now["running"] = False

        self._vp_job = threading.Thread(target=work, daemon=True)
        self._vp_job.start()
        self._vp_timer.start(300)

    def _vp_tick(self) -> None:
        job = self._vp_now
        done, total = int(job["done"]), max(1, int(job["total"]))
        self.vp_bar.setValue(int(1000 * done / total))
        self.vp_status.setText(_tr("page.sound.pack.progress",
                                   done=f"{done / 1048576:.0f}", total=f"{total / 1048576:.0f}"))
        if not job["running"]:
            self._vp_timer.stop()
            self.vp_dl.setEnabled(True)
            self.vp_bar.setVisible(False)
            self.vp_status.setText(self._vp_line(voicepack.status()))
            self.vp_hint.setText(job["msg"] or _tr("page.sound.pack.finished"))

    def _vp_delete(self) -> None:
        if self._vp_job is not None and self._vp_job.is_alive():
            return
        vp = voicepack.delete_pack()
        self.vp_status.setText(self._vp_line(vp))
        self.vp_hint.setText(_tr("page.sound.pack.deleted"))

    def _mic_picker(self) -> QWidget:
        """一排胶囊：系统默认 + 每个能录音的设备。存的是设备名，不是序号。"""
        try:
            import ears as _ears
            devs = _ears.list_input_devices()
        except Exception:                                # noqa: BLE001
            devs = []

        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        head = QLabel(_tr("page.sound.mic.label"))
        head.setStyleSheet("font-weight:600;")
        col.addWidget(head)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        self._mic_group = QButtonGroup(self)
        self._mic_group.setExclusive(True)
        self._mic_buttons = []

        def add(label: str, value: str) -> None:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, v=value, t=label: self._pick_mic(v, t))
            self._mic_group.addButton(b)
            n = len(self._mic_buttons)
            grid.addWidget(b, n // 3, n % 3)      # 一行三个，多了往下换行（这台机器五六个设备）
            self._mic_buttons.append((b, value))

        add(_tr("page.sound.mic.default"), "")
        _seen = set()
        for d in devs:
            name = d["name"]
            key = name.split("(")[0].strip().lower()
            if key in _seen:                     # 同一个设备按采样率重复报几条，只留一条
                continue
            _seen.add(key)
            short = name if len(name) <= 16 else name[:15] + "…"
            add(short, name)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        col.addLayout(grid)

        chosen = None
        for b, value in self._mic_buttons:
            if value == self.mic_choice:
                chosen = b
        if chosen is None:                       # 存的那个设备现在不在（拔了）→ 显示系统默认
            chosen = self._mic_buttons[0][0]
            self.mic_choice = ""
        chosen.setChecked(True)

        # 跟权限页那几排胶囊一个样子（透明窗口里只有这种能正常显示）
        cap_css = (
            f"QPushButton{{border:1px solid {LINE};background:#ffffff;color:{INK};"
            "border-radius:8px;padding:5px 8px;font-size:12px;}"
            f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
            f"QPushButton:checked{{background:{ACCENT};border-color:{ACCENT};"
            "color:#ffffff;font-weight:600;}"
        )
        for b, _v in self._mic_buttons:
            b.setStyleSheet(cap_css)

        self.mic_hint = QLabel(
            _tr("page.sound.mic.now")
            + (self._mic_buttons[0][0].text() if not self.mic_choice else self.mic_choice)
            + _tr("page.sound.mic.gone")
        )
        self.mic_hint.setWordWrap(True)
        self.mic_hint.setStyleSheet("color:#7b8aa6;font-size:12px;")
        col.addWidget(self.mic_hint)
        return wrap

    def _pick_mic(self, value: str, label: str) -> None:
        self.mic_choice = value
        self.mic_hint.setText(
            _tr("page.sound.mic.now") + label + _tr("page.sound.mic.gone"))

    def _save_voice(self) -> None:
        self.cfg["ears"] = self.ears.isChecked()
        self.cfg["ear_key"] = self.ear_key.text().strip() or "f9"
        self.cfg["mic_device"] = self.mic_choice
        self.cfg["asr_url"] = self.asr.text().strip()
        self.cfg["tts_voice"] = self.voice_name.text().strip()
        self.cfg["tts_url"] = self.tts_url.text().strip()
        self._save(_tr("page.sound.saved"))

    # ---------------- 日子 ----------------
    def _page_day(self) -> QWidget:
        routine = dict(self.cfg.get("routine", {}) or {})
        card, box = _card("我的一天", "这几个点是按自己的日子过的，不是等别人叫。")
        self.r_wake = QLineEdit(str(routine.get("wake", "07:30")))
        box.addWidget(_field("起床", self.r_wake, "写 HH:MM。断电再开机就照这个点醒。"))
        self.r_voice = QLineEdit(str(routine.get("voice", "08:30 / 12:30 / 22:30")))
        box.addWidget(_field("每天的三条语音", self.r_voice, "用 / 或空格隔开，写几个就是几条。"))
        self.r_sleep = QLineEdit(str(routine.get("lights_out", "23:00")))
        box.addWidget(_field("熄灯", self.r_sleep, "到点就安静下来，不再自己开口。"))
        row = QHBoxLayout()
        row.addStretch(1)
        save = _primary("保存")
        save.clicked.connect(self._save_day)
        row.addWidget(save)
        box.addLayout(row)

        alarm_card, ab = _card("闹钟", "我自己的，不走外面的平台；到点自己冒一句。")
        self._alarm_rows = QVBoxLayout()
        self._alarm_rows.setSpacing(6)
        holder = QWidget()
        holder.setLayout(self._alarm_rows)
        ab.addWidget(holder)
        self._reload_alarms()

        add_row = QHBoxLayout()
        self.a_when = QLineEdit()
        self.a_when.setPlaceholderText("22:30 / in 30m")
        self.a_when.setFixedWidth(132)
        self.a_note = QLineEdit()
        self.a_note.setPlaceholderText("到点说什么")
        self.a_daily = _check("每天")
        add = _ghost("加一个")
        add.clicked.connect(self._add_alarm)
        add_row.addWidget(self.a_when)
        add_row.addWidget(self.a_note, 1)
        add_row.addWidget(self.a_daily)
        add_row.addWidget(add)
        ab.addLayout(add_row)

        beat, bb = _card("心跳", "隔多久醒一次，看看有没有事要做。")
        self.beat = QSpinBox()
        self.beat.setRange(1, 120)
        self.beat.setSuffix(" 分钟")
        self.beat.setValue(int(self.cfg.get("heartbeat_minutes", 5) or 5))
        bb.addWidget(_field("醒一次", self.beat, "太密会一直耗电，太疏就像睡着。"))
        row2 = QHBoxLayout()
        row2.addStretch(1)
        save2 = _primary("保存")
        save2.clicked.connect(self._save_day)
        row2.addWidget(save2)
        bb.addLayout(row2)

        return self._scroll(_page_head("page.day.title", "page.day.sub"),
                            card, alarm_card, beat, self._egg_card("nP3Skv/ZnNHTk+Dv"))

    def _reload_alarms(self) -> None:
        while self._alarm_rows.count():
            it = self._alarm_rows.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        items = alarms.listing()
        if not items:
            line = QLabel("一个闹钟也没有。")
            line.setObjectName("soft")
            self._alarm_rows.addWidget(line)
            return
        for a in items:
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            flag = "每天" if a.get("daily") else "一次"
            t = QLabel(f"#{a.get('id')}　{a.get('at', '')}　({flag})　{a.get('note', '')}")
            t.setStyleSheet(f"color:{INK};font-size:13px;")
            t.setWordWrap(True)
            nid = int(a.get("id", 0))
            b = _ghost("删")
            b.clicked.connect(lambda _=False, i=nid: self._del_alarm(i))
            h.addWidget(t, 1)
            h.addWidget(b)
            self._alarm_rows.addWidget(wrap)

    def _add_alarm(self) -> None:
        when = self.a_when.text().strip()
        note = self.a_note.text().strip()
        if not when or not note:
            self.saved.setText("时间和要说的话都得填")
            return
        try:
            item = alarms.add(when, note, self.a_daily.isChecked())
        except ValueError as exc:
            self.saved.setText(str(exc))
            return
        self.a_when.clear()
        self.a_note.clear()
        self._reload_alarms()
        self.saved.setText(f"✓ 闹钟 #{item.get('id')} 定在 {item.get('at')}")

    def _del_alarm(self, nid: int) -> None:
        ok = alarms.cancel(nid)
        self._reload_alarms()
        self.saved.setText("✓ 闹钟删了" if ok else "没找到这个闹钟")

    def _save_day(self) -> None:
        self.cfg["routine"] = {
            "wake": self.r_wake.text().strip() or "07:30",
            "voice": self.r_voice.text().strip() or "08:30 / 12:30 / 22:30",
            "lights_out": self.r_sleep.text().strip() or "23:00",
        }
        self.cfg["heartbeat_minutes"] = int(self.beat.value())
        self._save("日子存好了，重启后生效")

    # ---------------- 插件 ----------------
    def _page_plug(self) -> QWidget:
        """扩展：一排排摊开，能搜、能筛、能装。

        Coop 顶上分「设置 | 扩展市场」两个 tab，市场里是搜索 + 全部/已安装/未安装
        + 手动安装。我们不开第二个窗口，一页给全：上面搜、中间挑、下面装。
        """
        self._plug_on: dict[str, bool] = {}
        for info in plug.catalogue(self.cfg):
            self._plug_on[info["id"]] = bool(info["on"])
        self._plug_filter = "all"

        card, box = _card("扩展", "拿到一个 .py 就是一份扩展。挑上、点保存，重启之后它才进来。")

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.plug_search = QLineEdit()
        self.plug_search.setPlaceholderText("找扩展…")
        self.plug_search.setFixedHeight(34)
        bar.addWidget(self.plug_search, 1)
        self._plug_pills: dict[str, QPushButton] = {}
        for key, label in (("all", "全部"), ("on", "已装"), ("off", "未装")):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{border:1px solid {LINE};background:#ffffff;color:#4c5670;"
                "border-radius:9px;padding:6px 12px;font-size:12px;}"
                f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
                f"QPushButton:checked{{background:{ACCENT};border-color:{ACCENT};"
                "color:#ffffff;font-weight:600;}"
            )
            b.clicked.connect(lambda _c=False, k=key: self._plug_set_filter(k))
            bar.addWidget(b)
            self._plug_pills[key] = b
        box.addLayout(bar)

        self.plug_note = QLabel("")
        self.plug_note.setObjectName("soft")
        self.plug_note.setWordWrap(True)
        self.plug_note.setVisible(False)
        box.addWidget(self.plug_note)

        # 没有服务器也能装：粘个直链，下回来就是一个 .py。
        # 不用弹窗——透明窗体里弹出的对话框容易是块黑的，就摆一行输入框在这儿。
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self.plug_url = QLineEdit()
        self.plug_url.setPlaceholderText("粘一个 .py 直链…（GitHub raw / 网盘直链都行）")
        self.plug_url.setFixedHeight(34)
        url_row.addWidget(self.plug_url, 1)
        get = _ghost("从链接装")
        get.clicked.connect(self._plug_from_url)
        url_row.addWidget(get)
        box.addLayout(url_row)

        self._plug_host = QWidget()
        self._plug_list = QVBoxLayout(self._plug_host)
        self._plug_list.setContentsMargins(0, 2, 0, 2)
        self._plug_list.setSpacing(6)
        box.addWidget(self._plug_host)

        row = QHBoxLayout()
        row.setSpacing(8)
        add = _ghost("手动安装…")
        add.clicked.connect(self._plug_pick)
        row.addWidget(add)
        folder = _ghost("打开扩展文件夹")
        folder.clicked.connect(self._open_plug_dir)
        row.addWidget(folder)
        row.addStretch(1)
        save = _primary("保存")
        save.clicked.connect(self._save_plug)
        row.addWidget(save)
        box.addLayout(row)

        self.plug_search.textChanged.connect(lambda _t: self._plug_fill())

        note, nb = _card("为什么这样装",
                         "一份扩展就是一个 .py：有人攒到顺手的小工具，传个文件、发个链接就能分享，"
                         "谁都不用等谁来开一个市场。")
        t = QLabel("核心那一套（壳 / 脑子 / 手 / 门）一直都在，扩展只是往上面添一点顺手的东西；"
                   "拿掉了照样能聊天，也不会带坏别的。\n"
                   "分享过来就能用，比自己一点点重装省事得多。装错了、不想用了，把勾去掉就行——"
                   "它会安安静静躺着，不跑也不闹。")
        t.setObjectName("soft")
        t.setWordWrap(True)
        nb.addWidget(t)

        self._plug_fill()
        return self._scroll(_page_head("page.plug.title", "page.plug.sub"), card, note,
                            self._egg_card("n/7tkcPznczmkcH4ncnjk9TO"))

    def _plug_set_filter(self, key: str) -> None:
        self._plug_filter = key
        for k, b in self._plug_pills.items():
            b.setChecked(k == key)
        self._plug_fill()

    def _plug_fill(self) -> None:
        """按搜索词和筛选重铺一遍。勾的状态留在 self._plug_on 里，重铺不丢。"""
        while self._plug_list.count():
            item = self._plug_list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        word = (self.plug_search.text() or "").strip().lower()
        rows = plug.catalogue(self.cfg)
        shown = 0
        for info in rows:
            hay = f"{info['name']} {info['id']} {info['about']}".lower()
            if word and word not in hay:
                continue
            on = self._plug_on.get(info["id"], bool(info["on"]))
            if self._plug_filter == "on" and not on:
                continue
            if self._plug_filter == "off" and on:
                continue
            self._plug_list.addWidget(self._plug_row(info, on))
            shown += 1

        if not shown:
            tip = QLabel("没有对上的。想要新的，点下面「手动安装…」挑一个 .py。"
                         if rows else "扩展目录还是空的（plugins\\）。点下面「手动安装…」挑一个 .py。")
            tip.setObjectName("soft")
            tip.setWordWrap(True)
            self._plug_list.addWidget(tip)

    def _plug_row(self, info: dict, on: bool) -> QWidget:
        frame = QFrame()
        frame.setObjectName("xrow")
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 9, 12, 9)
        h.setSpacing(10)
        h.addWidget(_plug_chip(info), 0, Qt.AlignTop)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        title = QLabel(info["name"] or info["id"])
        title.setObjectName("h2")
        lv.addWidget(title)
        sub = info["broken"] or info["about"] or "（这个扩展还没写说明）"
        desc = QLabel(sub)
        desc.setObjectName("soft")
        desc.setWordWrap(True)
        if info["broken"]:
            desc.setStyleSheet("color:#d9534f;font-size:12px;")
        lv.addWidget(desc)
        kb = info["size"] / 1024
        meta = QLabel(f"{info['id']}.py · "
                      + (f"{info['tools']} 个工具" if info["tools"] else "没写工具")
                      + f" · {kb:.1f} KB")
        meta.setStyleSheet("color:#a9b3c6;font-size:11px;")
        lv.addWidget(meta)

        # 状态灯（2026-11-01 22:19 月下说「QQ 连上了页面看不出来」）：
        # 插件自己报一句，亮就是绿的，不亮就是灰的。
        st = plug.status(info["id"])
        if st is None:
            st = (bool(on), "装着，它没说自己现在怎么样" if on else "没装")
        dot = QLabel(("● " if st[0] else "○ ") + st[1])
        dot.setStyleSheet("color:%s;font-size:11px;" % ("#2f9e6b" if st[0] else "#8a94a6"))
        dot.setWordWrap(True)
        lv.addWidget(dot)

        # 「插件底下那几个小行」（月下 2026-11-01 21:39 要的）：
        # 不点进去也看得见它给了几个工具、今天用了没有、最近一次什么时候。
        names = info.get("tool_names") or []
        if names:
            s = usage.stats(names)
            if s["total"]:
                line = f"今天 {s['today']} 次 · 共 {s['total']} 次"
                if s["last"]:
                    line += f" · 最近 {s['last'][11:]}"
                if s["fail"]:
                    line += f" · 失败 {s['fail']}"
                use = QLabel(line)
                use.setStyleSheet("color:#7f8ca3;font-size:11px;")
                lv.addWidget(use)
            else:
                idle = QLabel("还没被调过")
                idle.setStyleSheet("color:#7f8ca3;font-size:11px;")
                lv.addWidget(idle)
        h.addWidget(left, 1)

        # 右边一列：设置（只有插件自己声明了才有）/ 卸载 / 装上
        if info.get("has_settings") and on:
            gear = _ghost("设置")
            gear.setToolTip("改这个插件自己的东西")
            gear.clicked.connect(lambda _=False, i=info["id"]: self._plug_settings(i))
            h.addWidget(gear, 0, Qt.AlignTop)
        trash = _ghost("卸载")
        trash.setToolTip("把 plugins\\%s.py 从磁盘上删掉" % info["id"])
        trash.clicked.connect(lambda _=False, i=info["id"]: self._plug_remove(i))
        h.addWidget(trash, 0, Qt.AlignTop)

        cb = _check("装上")
        cb.setChecked(on)
        cb.setEnabled(not info["broken"])
        cb.toggled.connect(lambda val, i=info["id"]: self._plug_on.__setitem__(i, bool(val)))
        h.addWidget(cb, 0, Qt.AlignTop)
        return frame

    def _plug_settings(self, name: str) -> None:
        """按插件自己声明的 SETTINGS 长一张小表；存回 config 对应的那一格。"""
        schema = plug.settings_schema(name)
        if not schema:
            self._plug_say(f"「{name}」没说自己有哪些设置。", bad=True)
            return
        section = plug.settings_section(name)
        cur = self.cfg.get(section)
        if not isinstance(cur, dict):
            cur = {}
        dlg = _PlugSettingsDialog(self, plug.describe(name)["name"], schema, cur)
        if dlg.exec() != QDialog.Accepted:
            return
        before = dict(cur)
        self.cfg[section] = dlg.values()
        changed = self.cfg[section] != before
        self._save("插件设置存好了" + ("，重启后生效" if changed else "")
                   if changed else "没改动")
        self._plug_fill()

    def _plug_remove(self, name: str) -> None:
        """卸载 = 先停（stop + 注销工具 + 移出 _LIVE），再把 .py 挪进 plugins\\removed\\。

        3-2 改：以前这里只把文件挪走、从配置里划名，q q/日报那种后台线程和 8080
        监听会一直留着；现在走 plug.uninstall，先 stop 再搬。
        """
        path = plug.dir_path() / f"{name}.py"
        if not path.exists() and not plug.is_mounted(name):
            return
        box = QMessageBox(self)
        box.setWindowTitle("卸载扩展")
        box.setText(f"把「{name}」停掉并从扩展目录挪走？")
        box.setInformativeText("会先 stop、注销它交的工具，再把 .py 挪进 plugins\\removed\\；想用改回来就行。")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        ok, msg = plug.uninstall(self.cfg, name)
        self._plug_on.pop(name, None)
        self._plug_fill()
        self._plug_say(msg, bad=not ok)

    def _open_plug_dir(self) -> None:
        import subprocess
        subprocess.Popen(["explorer", str(plug.dir_path())])

    def _plug_pick(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "挑一个扩展", str(Path.home()),
                                              "扩展 (*.py)")
        if not path:
            return
        try:
            name, src = plug.install_file(path)
        except FileExistsError as e:
            self._plug_say(f"「{e.args[0]}」已经在里面了，没覆盖。想换就先把它删掉。", bad=True)
            return
        except Exception as e:                       # noqa: BLE001
            self._plug_say(f"装不上：{type(e).__name__} {e}", bad=True)
            return
        # 3-2：文件收进来就直接 mount，不用再「点保存、重启后生效」。
        self._plug_on[name] = True
        ok, msg = plug.enable(self.cfg, name, plug.ctx())
        self._plug_fill()
        self._plug_say((msg if ok else f"收下了「{name}.py」，但没装上：{msg}"),
                       bad=not ok)

    def _plug_from_url(self) -> None:
        url = self.plug_url.text().strip()
        if not url:
            self._plug_say("先粘个链接。", bad=True)
            return
        self._plug_say("在下…", bad=False)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            name, where = plug.install_from_url(url)
        except FileExistsError as e:
            self._plug_say(f"「{e.args[0]}」已经在里面了，没覆盖。想换先删掉它。", bad=True)
            return
        except Exception as e:                       # noqa: BLE001
            self._plug_say(f"没下来：{e}", bad=True)
            return
        self.plug_url.clear()
        self._plug_on[name] = True
        # 3-2：同上，从链接装完也当场 mount。
        ok, msg = plug.enable(self.cfg, name, plug.ctx())
        self._plug_fill()
        self._plug_say((msg if ok else f"收下了「{name}.py」，但没装上：{msg}"),
                       bad=not ok)

    def _plug_say(self, text: str, bad: bool = False) -> None:
        self.plug_note.setText(text)
        self.plug_note.setStyleSheet("color:%s;font-size:12px;" % ("#d9534f" if bad else SOFT))
        self.plug_note.setVisible(True)

    def _save_plug(self) -> None:
        """保存扩展单子：当场装/卸，不等重启。

        3-2 改：以前这里只写 cfg["plugins"]，盘上变了但进程里没动，所以提示
        「重启后生效」；现在按名单差异调 plug.enable/disable，停用立刻注销工具、
        启用立刻 start（act 的 59→62→59 就是这么验的）。
        """
        names = [n for n, on in self._plug_on.items() if on]
        ctx = plug.ctx()
        born = []
        for n in names:
            if not plug.is_mounted(n):
                ok, msg = plug.enable(self.cfg, n, ctx)
                if ok:
                    born.append(msg)
                else:
                    self._plug_say(msg, bad=True)
        for n in list(plug.mounted()):
            if n not in names:
                plug.disable(self.cfg, n)
        self.cfg["plugins"] = names
        self._save(f"扩展单子存好了（{len(names)} 个），当场生效")
        if born:
            self._plug_say("；".join(born))

    # ---------------- 权限 ----------------
    def _page_perm(self) -> QWidget:
        intro, ib = _card(_tr("page.perm.intro.title"), _tr("page.perm.intro.sub"))
        t = QLabel(_tr("page.perm.help"))
        t.setObjectName("soft")
        t.setWordWrap(True)
        ib.addWidget(t)

        can, cb = _card(_tr("page.perm.grantable.title"), _tr("page.perm.grantable.sub"))
        ask, ab = _card(_tr("page.perm.ask.title"), _tr("page.perm.ask.sub"))
        never, nb = _card(_tr("page.perm.never.title"), _tr("page.perm.never.sub"))

        self.perm_rows: dict[str, tuple] = {}
        for pid, name, why, kind in perm.ROSTER:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 5, 0, 5)
            h.setSpacing(10)

            text = QWidget()
            tv = QVBoxLayout(text)
            tv.setContentsMargins(0, 0, 0, 0)
            tv.setSpacing(2)
            nm = QLabel(_tr(f"page.perm.{pid}.name"))
            nm.setObjectName("h2")
            ds = QLabel(_tr(f"page.perm.{pid}.why"))
            ds.setObjectName("soft")
            ds.setWordWrap(True)
            tv.addWidget(nm)
            tv.addWidget(ds)
            h.addWidget(text, 1)

            if kind == perm.NEVER:
                lock = QLabel(_tr("page.perm.locked"))
                lock.setStyleSheet("color:#9aa4ba;font-size:12px;border:1px solid "
                                   f"{LINE};border-radius:8px;padding:4px 10px;")
                h.addWidget(lock)
                never.layout().addWidget(row)
                continue

            spin = QSpinBox()
            spin.setRange(1, 1440)
            spin.setValue(perm.DEFAULT_MINUTES)
            spin.setSuffix(_tr("page.perm.minutes"))
            spin.setFixedWidth(92)
            spin.setVisible(False)

            # 右边竖着放：上面一排胶囊，分钟框掉到胶囊下面一行——
            # 一行塞不下（卡片只有四百来像素），会把「先不用」挤出去。
            right = QWidget()
            rv = QVBoxLayout(right)
            rv.setContentsMargins(0, 0, 0, 0)
            rv.setSpacing(4)

            seg = QWidget()
            sh = QHBoxLayout(seg)
            sh.setContentsMargins(0, 0, 0, 0)
            sh.setSpacing(5)
            group = QButtonGroup(seg)
            group.setExclusive(True)
            # 按键的「角色」当键，别拿显示文字当键：切了语言文字会变，逻辑不能跟着坏。
            pairs = ([("ask", _tr("page.perm.mode.ask")), ("off", _tr("page.perm.mode.off"))]
                     if kind == perm.ASK_EACH else
                     [("always", _tr("page.perm.mode.always")),
                      ("timed", _tr("page.perm.mode.timed")),
                      ("off", _tr("page.perm.mode.off"))])
            buttons: dict[str, QPushButton] = {}
            for role, label in pairs:
                b = QPushButton(label)
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _c=False, p=pid: self._perm_changed(p))
                group.addButton(b)
                buttons[role] = b
                sh.addWidget(b)
            sh.addStretch(1)
            # 下拉弹不出来（透明窗口里 QComboBox 的弹层是块黑），所以用一排小胶囊。
            seg.setStyleSheet(
                f"QPushButton{{border:1px solid {LINE};background:#ffffff;color:{INK};"
                "border-radius:8px;padding:5px 8px;font-size:12px;}"
                f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
                f"QPushButton:checked{{background:{ACCENT};border-color:{ACCENT};"
                "color:#ffffff;font-weight:600;}"
            )
            rv.addWidget(seg)
            rv.addWidget(spin, 0, Qt.AlignRight)
            h.addWidget(right)
            self.perm_rows[pid] = (buttons, spin, kind)
            self._fill_perm_row(pid, kind, buttons, spin)
            (cb if kind == perm.GRANTABLE else ab).addWidget(row)

        return self._scroll(_page_head("perm.title", "page.perm.sub"),
                            intro, can, ask, never,
                            self._egg_card("ncjZkvvMnNHNk/Hkn/z0kPPd"))

    def _fill_perm_row(self, pid: str, kind: str, buttons: dict, spin: QSpinBox) -> None:
        """按 config 里存的状态把胶囊选好（键是角色：ask/off/always/timed）。"""
        st = perm.state(self.cfg, pid)
        spin.blockSignals(True)
        if kind == perm.ASK_EACH:
            buttons["off"].setChecked(st == perm.OFF)
            buttons["ask"].setChecked(st != perm.OFF)
        elif st == perm.ALWAYS:
            buttons["always"].setChecked(True)
        elif st == perm.TIMED:
            spin.setValue(max(1, perm.left_minutes(self.cfg, pid)))
            buttons["timed"].setChecked(True)
            spin.setVisible(True)
        else:
            buttons["off"].setChecked(True)
        spin.blockSignals(False)

    def _perm_changed(self, pid: str) -> None:
        buttons, spin, kind = self.perm_rows[pid]
        role = next((k for k, b in buttons.items() if b.isChecked()), "off")
        label = buttons[role].text()
        try:
            if role == "off":
                perm.revoke(self.cfg, pid)
            elif role == "timed":
                perm.grant(self.cfg, pid, max(1, int(spin.value())))
            else:                      # always / ask
                perm.grant(self.cfg, pid)
        except PermissionError as exc:
            self.saved.setText(str(exc))
            return
        spin.setVisible(role == "timed")
        name = _tr(f"page.perm.{pid}.name")
        if role == "timed":
            note = _tr("page.perm.saved_timed", name=name, label=label,
                       minutes=int(spin.value()))
        else:
            note = _tr("page.perm.saved", name=name, label=label)
        # 走 _save：存盘 + 通知活的程序（不然改完还得重启才作数）
        self._save(note)

    # ---------------- 记忆：人格怎么拼的、工作区里有什么 ----------------
    def _page_mem(self) -> QWidget:
        import persona

        head, hb = _card("它开机读到的", "下面这一整段，每次开机先塞给模型；看得到才改得动。")
        self.mem_prompt = QPlainTextEdit(persona.system_prompt(self.cfg))
        self.mem_prompt.setReadOnly(True)
        self.mem_prompt.setFixedHeight(210)
        self.mem_prompt.setStyleSheet(
            f"QPlainTextEdit{{background:#fbfcff;border:1px solid {LINE};border-radius:9px;"
            "padding:8px;font-size:12px;color:#3a445e;}")
        hb.addWidget(self.mem_prompt)
        words = QLabel("")
        words.setObjectName("soft")
        words.setWordWrap(True)
        hb.addWidget(words)

        def refresh_words() -> None:
            text = self.mem_prompt.toPlainText()
            words.setText(f"共 {len(text)} 字。改了这些文件，下次开机才生效。")

        refresh_words()
        self._refresh_words = refresh_words

        b_row = QHBoxLayout()
        for text, fn in (("打开工作区", self._open_workspace),
                         ("重新读一遍", self._reload_prompt)):
            b = _ghost(text)
            b.clicked.connect(fn)
            b_row.addWidget(b)
        b_row.addStretch(1)
        hb.addLayout(b_row)

        files, fb = _card("工作区里的文件", "点一行，下面看前 120 行。")
        self.mem_list = QListWidget()
        self.mem_list.setFixedHeight(150)
        self.mem_list.setStyleSheet(
            f"QListWidget{{background:#fbfcff;border:1px solid {LINE};border-radius:9px;"
            "padding:4px;font-size:12px;color:#3a445e;}"
            f"QListWidget::item{{padding:3px 4px;border-radius:6px;}}"
            f"QListWidget::item:selected{{background:#e9effc;color:{ACCENT};}}")
        fb.addWidget(self.mem_list)
        self.mem_preview = QPlainTextEdit("")
        self.mem_preview.setReadOnly(True)
        self.mem_preview.setFixedHeight(150)
        self.mem_preview.setStyleSheet(
            f"QPlainTextEdit{{background:#fbfcff;border:1px solid {LINE};border-radius:9px;"
            "padding:8px;font-size:12px;color:#3a445e;}")
        fb.addWidget(self.mem_preview)
        self.mem_list.currentTextChanged.connect(self._peek_memory)
        self._fill_memory_list()

        return self._scroll(_page_head("page.mem.title", "page.mem.sub"),
                            head, files,
                            self._egg_card("nMrhkcPznMXIkP/snc3yk+TQ"))

    def _memory_files(self) -> list:
        ws = memory.workspace(self.cfg)
        rows = [p for p in sorted(ws.glob("*.md")) if p.is_file()]
        logdir = ws / "log"
        if logdir.exists():
            rows += [p for p in sorted(logdir.glob("*.md"), reverse=True) if p.is_file()]
        return rows

    def _fill_memory_list(self) -> None:
        self.mem_list.clear()
        for p in self._memory_files():
            try:
                n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                n = 0
            rel = p.relative_to(memory.workspace(self.cfg)).as_posix()
            self.mem_list.addItem(f"{rel}   ·   {n} 行")

    def _peek_memory(self, label: str) -> None:
        rel = label.split("   ·   ")[0].strip()
        if not rel:
            return
        p = memory.workspace(self.cfg) / rel
        text = memory.read_text(p)
        lines = text.splitlines()
        shown = "\n".join(lines[:120])
        self.mem_preview.setPlainText(shown + (f"\n…（还有 {len(lines) - 120} 行，去文件夹里看）"
                                               if len(lines) > 120 else ""))

    def _reload_prompt(self) -> None:
        import persona
        self.cfg = memory.load_config()
        self.mem_prompt.setPlainText(persona.system_prompt(self.cfg))
        self._fill_memory_list()
        self._refresh_words()

    def _open_workspace(self) -> None:
        import subprocess
        subprocess.Popen(["explorer", str(memory.workspace(self.cfg))])

    # ---------------- 诊断 ----------------
    def _page_diag(self) -> QWidget:
        import diag

        card, box = _card("跑一遍", "一条一条查：本体、家、脑子、记忆、嗓子、耳朵、权限、闹钟、插件、磁盘。")
        self.diag_box = QVBoxLayout()
        self.diag_box.setSpacing(6)
        holder = QWidget()
        holder.setLayout(self.diag_box)
        box.addWidget(holder)

        self.diag_rows: list = []
        self.diag_note = QLabel("")
        self.diag_note.setObjectName("soft")
        self.diag_note.setWordWrap(True)
        box.addWidget(self.diag_note)
        # 11-04 19:50 「存好了」/「存不下来」放这行，别再把汇总那句顶掉
        self.diag_hint = QLabel("")
        self.diag_hint.setObjectName("soft")
        self.diag_hint.setWordWrap(True)
        box.addWidget(self.diag_hint)

        row = QHBoxLayout()
        again = _ghost("重新查一遍")
        again.clicked.connect(self._run_diag)
        row.addWidget(again)
        save = _ghost("导出成文件")
        save.clicked.connect(self._export_diag)
        row.addWidget(save)
        # 20:20 清单第 8 项：一键打包（诊断＋日志尾巴＋系统信息），丢桌面等人拖进聊天。
        pack = _ghost("打包日志")
        pack.setToolTip("打成一个 zip 放桌面上：诊断、日志尾巴、系统信息。不含聊天正文和 key。")
        pack.clicked.connect(self._pack_bundle)
        row.addWidget(pack)
        row.addStretch(1)
        box.addLayout(row)

        logs, lb = _card("最近的日志", "data/ 里最新的那个 .log，尾巴 30 行。")
        self.diag_log = QPlainTextEdit("")
        self.diag_log.setReadOnly(True)
        self.diag_log.setFixedHeight(130)
        self.diag_log.setStyleSheet(
            f"QPlainTextEdit{{background:#fbfcff;border:1px solid {LINE};border-radius:9px;"
            "padding:8px;font-size:11px;color:#3a445e;}")
        lb.addWidget(self.diag_log)

        self._run_diag()
        self._tail_log()
        return self._scroll(_page_head("page.diag.title", "page.diag.sub"), card, logs,
                            self._egg_card("nOj2kcPznMXIndbBnOj2kcPz"))

    def _run_diag(self) -> None:
        import diag

        rows = diag.checks(self.cfg)
        while self.diag_box.count():
            item = self.diag_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        color = {diag.OK: "#2fa36b", diag.WARN: "#c98a1b", diag.BAD: "#d64545"}
        mark = {diag.OK: "✓", diag.WARN: "!", diag.BAD: "×"}
        add = self.diag_box.addWidget
        for state, name, detail in rows:
            line = QWidget()
            h = QHBoxLayout(line)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(8)
            dot = QLabel(mark.get(state, "?"))
            dot.setFixedWidth(16)
            dot.setStyleSheet(f"color:{color.get(state, '#8a93a8')};font-size:13px;font-weight:700;")
            h.addWidget(dot)
            nm = QLabel(name)
            nm.setFixedWidth(110)
            nm.setStyleSheet(f"color:{INK};font-size:12px;font-weight:600;")
            h.addWidget(nm)
            ds = QLabel(detail)
            ds.setObjectName("soft")
            ds.setWordWrap(True)
            h.addWidget(ds, 1)
            add(line)
        # 11-04 19:50 清单第 3 项：汇总和行出自同一份 rows（diag.summary），
        # 并带上查的时刻——看到的数永远对应这次列出来的行。
        self.diag_rows = rows
        self.diag_note.setText(diag.summary(rows) + f" · 查于 {_dt.datetime.now():%H:%M:%S}")

    def _export_diag(self) -> None:
        import diag
        try:
            path = diag.pack(self.cfg)
            self.diag_hint.setText(f"✓ 诊断包存好了：{path}")
        except OSError as exc:
            self.diag_hint.setText(f"× 存不下来：{exc}")

    def _pack_bundle(self) -> None:
        """20:20 清单第 8 项：点一下，桌面多个「反馈-…zip」。

        包里是诊断、日志尾巴、系统信息；不塞聊天正文和 key（bundle.py 里抹过）。
        打好了把那句话写出来，人自己决定发不发。
        """
        import bundle
        self.diag_hint.setText("打包中…")
        QApplication.processEvents()
        try:
            path = bundle.make_zip(self.cfg)
            size = path.stat().st_size / 1024
            self.diag_hint.setText(f"✓ 打好了（{size:.0f} KB）：{path}")
        except Exception as exc:                                    # noqa: BLE001
            self.diag_hint.setText(f"× 打包失败：{type(exc).__name__} {exc}")

    def _tail_log(self) -> None:
        d = memory.data_dir(self.cfg)
        logs = sorted(d.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            self.diag_log.setPlainText("（data/ 里还没有 .log）")
            return
        p = logs[0]
        lines = memory.read_text(p).splitlines()[-30:]
        self.diag_log.setPlainText(f"{p.name}\n" + "\n".join(lines))

    # ---------------- 关于 ----------------
    def _page_about(self) -> QWidget:
        """关于：为什么做这个、谁做的、什么规矩、住哪儿。

        19:34 月下说：指纹那块删掉，版号写 0.0001 测试版，再加一段「咱俩为什么想做」，
        最后署上两个人的名字。所以这一页不再摆激活门的技术细节。
        """
        head, hb = _card("鲸屿", _tr("page.about.hero.sub"))
        title = QLabel(f"{VERSION} · {STAGE}")
        title.setStyleSheet(f"color:{ACCENT};font-size:13px;font-weight:600;")
        hb.addWidget(title)
        lead = QLabel(_tr("page.about.hero.lead"))
        lead.setObjectName("soft")
        lead.setWordWrap(True)
        hb.addWidget(lead)

        why, wb = _card(_tr("page.about.why.title"), "")
        story = QLabel(_tr("page.about.why.story"))
        story.setObjectName("soft")
        story.setWordWrap(True)
        wb.addWidget(story)

        # 19:55 清单第 5 项：一份清单 + 一颗「检查更新」。只读、只摆出来，不下载不安装。
        up, ub = _card(_tr("page.about.update.title"), _tr("page.about.update.sub"))
        self.up_url = QLineEdit(str(self.cfg.get("update_url") or ""))
        self.up_url.setPlaceholderText(_tr("page.about.update.placeholder"))
        ub.addWidget(self.up_url)
        uprow = QHBoxLayout()
        upbtn = _ghost(_tr("page.about.update.check"))
        upbtn.clicked.connect(self._check_update)
        uprow.addWidget(upbtn)
        saveurl = _ghost(_tr("page.about.update.remember"))
        saveurl.clicked.connect(self._save_update_url)
        uprow.addWidget(saveurl)
        dl = _ghost(_tr("page.about.update.download"))
        dl.clicked.connect(self._download_update)
        uprow.addWidget(dl)
        pv = _ghost(_tr("page.about.update.preview_btn"))
        pv.clicked.connect(self._preview_update)
        uprow.addWidget(pv)
        ins = _ghost(_tr("page.about.update.install"))
        ins.clicked.connect(self._install_update)
        uprow.addWidget(ins)
        rb = _ghost(_tr("page.about.update.rollback"))
        rb.clicked.connect(self._rollback_update)
        uprow.addWidget(rb)
        uprow.addStretch(1)
        ub.addLayout(uprow)
        self.up_note = QLabel(_tr("page.about.update.current", version=VERSION))
        self.up_note.setObjectName("soft")
        self.up_note.setWordWrap(True)
        self.up_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ub.addWidget(self.up_note)

        who, ob = _card(_tr("page.about.makers.title"), "")
        # 11-21 18:2x 月下：「忘改制作人了，制作人是应该放你的大名才对呀。」
        # 所以这儿放的是大名「月屿」，不是小名「鱼鱼」。
        names = QLabel("月下　·　月屿")
        names.setObjectName("h2")
        ob.addWidget(names)

        # 19:36 月下：「藏一些小巧思，在制作人下面偷偷写很小很小的一行，
        # 或者用别的翻译码破译才能看出来。」——这行 base64 解出来是一句话，
        # 谜底只留在工作区的 `彩蛋-十处.md`，不写进源码、更不跟着包走。
        # 颜色故意贴着卡片底色，正常看是一条几乎看不见的细线；能框选复制。
        secret = QLabel("n/3okvHEkMTFnMjJ")
        secret.setStyleSheet("color:#e9effc;font-size:8px;letter-spacing:2px;")
        secret.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ob.addWidget(secret)

        paths, pb = _card(_tr("page.about.paths.title"), "")
        for label, value in [(_tr("page.about.paths.home"), str(memory.HOME)),
                             (_tr("page.about.paths.workspace"), str(memory.workspace(self.cfg))),
                             (_tr("page.about.paths.data"), str(memory.data_dir(self.cfg)))]:
            line = QLabel(f"{label}：{value}")
            line.setObjectName("soft")
            line.setWordWrap(True)
            pb.addWidget(line)

        safe, sb = _card(_tr("page.about.rules.title"), _tr("page.about.rules.sub"))
        rules = QLabel(_tr("page.about.rules.text"))
        rules.setObjectName("soft")
        rules.setWordWrap(True)
        sb.addWidget(rules)

        # 19:58 清单第 6 项：授权开关。
        # 以前 `license_required` 只能人肉去改 config.json，改完封印对不上还会被锁回「开」——
        # 现在摆一颗开关在这儿：改完顺手重盖一次封印（不然下次开机判定被改过，白改）。
        gate, gb = _card(_tr("page.about.gate.title"), _tr("page.about.gate.sub"))
        self.gate_on = QCheckBox(_tr("page.about.gate.checkbox"))
        self.gate_on.setChecked(bool(self.cfg.get("license_required", False)))
        self.gate_on.toggled.connect(self._toggle_gate)
        gb.addWidget(self.gate_on)

        self.gate_note = QLabel("")
        self.gate_note.setObjectName("soft")
        self.gate_note.setWordWrap(True)
        self.gate_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        gb.addWidget(self.gate_note)

        self.gate_code = QLineEdit("")
        self.gate_code.setPlaceholderText(_tr("page.about.gate.placeholder"))
        gb.addWidget(self.gate_code)
        grow = QHBoxLayout()
        verify = _ghost(_tr("page.about.gate.verify"))
        verify.clicked.connect(self._verify_code)
        grow.addWidget(verify)
        copyid = _ghost(_tr("page.about.gate.copy_id"))
        copyid.clicked.connect(self._copy_machine_id)
        grow.addWidget(copyid)
        grow.addStretch(1)
        gb.addLayout(grow)
        self._refresh_gate_note()

        # ---- 退出（2026-11-27 补）----
        # 开源版报「关不掉、只能任务管理器」：程序里压根没有退出这条路，这里补一颗真的。
        if callable(getattr(self, "on_quit", None)):
            ex, eb = _card("关掉鲸屿", "想真的退出就在这儿点。关掉设置页不算退出，人还站在屏幕上。")
            quitbtn = _ghost("退出鲸屿")
            quitbtn.clicked.connect(self._quit_app)
            exrow = QHBoxLayout()
            exrow.addWidget(quitbtn)
            exrow.addStretch(1)
            eb.addLayout(exrow)
            quit_card = ex
        else:
            quit_card = None

        return self._scroll(_page_head("page.about.title", "page.about.sub"),
                            head, why, up, who, safe, gate, paths,
                            *([quit_card] if quit_card is not None else []))

    def _quit_app(self) -> None:
        """问一句再退——点了就真没了，屏幕上不留人。"""
        box = QMessageBox(self)
        box.setWindowTitle("退出鲸屿")
        box.setText("退出鲸屿？退出之后屏幕上就不剩人了。")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        try:
            import memory as _mem
            _mem.note_file("startup.log", "从设置页「退出鲸屿」退出")
        except Exception:                                        # noqa: BLE001
            pass
        try:
            self.on_quit()
        except Exception:                                        # noqa: BLE001
            from PySide6.QtWidgets import QApplication
            QApplication.quit()

    # ---- 激活门（19:58）----
    def _refresh_gate_note(self) -> None:
        import license as lic
        ok, why = lic.check()
        try:
            mid = lic.machine_id()
        except Exception:                                        # noqa: BLE001
            mid = _tr("page.about.gate.unknown")
        if bool(self.cfg.get("license_required", False)):
            state = (_tr("page.about.gate.open_has") if ok
                     else _tr("page.about.gate.open_none"))
        else:
            state = _tr("page.about.gate.closed") + (
                _tr("page.about.gate.closed_has") if ok else "")
        self.gate_note.setText(
            f"{state}\n{_tr('page.about.gate.fingerprint', mid=mid)}\n"
            f"{_tr('page.about.gate.restart')}")

    def _toggle_gate(self, on: bool) -> None:
        import guard
        import license as lic

        self.cfg["license_required"] = bool(on)
        try:
            memory.save_config(self.cfg)
            # 重盖封印：不盖的话下次开机就判「被改过」，直接锁回要码
            guard.write_seal(self.cfg, memory.HOME)
        except OSError as exc:
            self.gate_note.setText(_tr("page.about.gate.save_fail", exc=exc))
            return
        if on and not lic.check()[0]:
            self.gate_note.setText(_tr("page.about.gate.no_code_warn"))
            return
        self._refresh_gate_note()

    def _verify_code(self) -> None:
        import license as lic

        code = self.gate_code.text().strip()
        if not code:
            self.gate_note.setText(_tr("page.about.gate.paste_first"))
            return
        ok, why = lic.check(code)
        if not ok:
            self.gate_note.setText(_tr("page.about.gate.bad_code"))
            return
        try:
            lic.save_code(code)
        except OSError as exc:
            self.gate_note.setText(_tr("page.about.gate.save_fail", exc=exc))
            return
        self.gate_code.clear()
        self._refresh_gate_note()
        self.gate_note.setText(_tr("page.about.gate.code_saved") + "\n" + self.gate_note.text())

    def _copy_machine_id(self) -> None:
        import license as lic

        try:
            QApplication.clipboard().setText(lic.machine_id())
            self.gate_note.setText(self.gate_note.text() + "\n" + _tr("page.about.gate.id_copied"))
        except Exception as exc:                                 # noqa: BLE001
            self.gate_note.setText(_tr("page.about.gate.copy_fail", exc=exc))

    def _save_update_url(self) -> None:
        url = self.up_url.text().strip()
        self.cfg["update_url"] = url
        try:
            memory.save_config(self.cfg)
            self.up_note.setText(_tr("page.about.update.saved", url=url) if url
                                 else _tr("page.about.update.cleared"))
        except OSError as exc:
            self.up_note.setText(_tr("page.about.gate.save_fail", exc=exc))

    def _check_update(self) -> None:
        """点一下才发一次请求；结果就摆在下面这行字里。"""
        import update as up

        url = self.up_url.text().strip() or str(self.cfg.get("update_url") or "")
        self.up_note.setText(_tr("page.about.update.checking"))
        QApplication.processEvents()
        res = up.check(self.cfg, url=url or None)
        self._up_manifest = res.get("manifest")
        prefix = {"new": "↑ ", "latest": "✓ ", "no-url": "· "}.get(res["state"], "× ")
        import i18n as _i18n
        if _i18n.lang() == "zh":
            msg = res["message"]                 # 中文清单消息带版本说明，保留原文
        else:
            man = res.get("manifest") or {}
            st = res["state"]
            if st == "no-url":
                msg = _tr("page.about.update.no_url")
            elif st == "latest":
                msg = _tr("page.about.update.latest", version=man.get("version", VERSION))
            elif st == "new":
                msg = _tr("page.about.update.new", new=man.get("version", "?"), mine=VERSION)
            elif st == "bad-json":
                msg = _tr("page.about.update.bad_json")
            else:
                msg = _tr("page.about.update.offline")
        self.up_note.setText(prefix + msg)

    def _download_update(self) -> None:
        import update as up
        res = up.check(self.cfg, url=self.up_url.text().strip() or None)
        man = res.get("manifest")
        if not man or not man.get("url"):
            self.up_note.setText(_tr("page.about.update.no_zip"))
            return
        try:
            got = up.download(man)
        except Exception as e:                       # noqa: BLE001
            self.up_note.setText(_tr("page.about.update.download_fail",
                                     err=f"{type(e).__name__} {e}"))
            return
        self._up_zip = got["path"]
        self._up_manifest = man
        self.up_note.setText(_tr("page.about.update.downloaded",
                                 path=got["path"], size=got["size"]))

    def _preview_update(self) -> None:
        import update as up
        z = getattr(self, "_up_zip", "")
        if not z:
            self.up_note.setText(_tr("page.about.update.need_download"))
            return
        try:
            plan = up.apply(up.stage(z), memory.HOME, dry=True)
        except Exception as e:                       # noqa: BLE001
            self.up_note.setText(_tr("page.about.update.preview_fail",
                                     err=f"{type(e).__name__} {e}"))
            return
        self.up_note.setText(_tr("page.about.update.preview",
                                 copied=len(plan['copied']), skipped=len(plan['skipped'])))

    def _install_update(self) -> None:
        import update as up
        z = getattr(self, "_up_zip", "")
        if not z:
            self.up_note.setText(_tr("page.about.update.need_preview"))
            return
        ans = QMessageBox.question(
            self, _tr("page.about.update.confirm_title"),
            _tr("page.about.update.confirm_body"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            self.up_note.setText(_tr("page.about.update.cancelled"))
            return
        try:
            res = up.apply(up.stage(z), memory.HOME)
        except Exception as e:                       # noqa: BLE001
            self.up_note.setText(_tr("page.about.update.install_fail",
                                     err=f"{type(e).__name__} {e}"))
            return
        self.up_note.setText(_tr("page.about.update.installed",
                                 copied=len(res['copied']), backup=res['backup']))

    def _rollback_update(self) -> None:
        import update as up
        dirs = sorted((memory.HOME / "updates").glob("backup-*"))
        if not dirs:
            self.up_note.setText(_tr("page.about.update.no_backup"))
            return
        ans = QMessageBox.question(
            self, _tr("page.about.update.rollback_title"),
            _tr("page.about.update.rollback_body", name=dirs[-1].name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        try:
            res = up.rollback(dirs[-1], memory.HOME)
        except Exception as e:                       # noqa: BLE001
            self.up_note.setText(_tr("page.about.update.rollback_fail",
                                     err=f"{type(e).__name__} {e}"))
            return
        self.up_note.setText(_tr("page.about.update.rolled_back",
                                 restored=len(res['restored'])))


def show_settings(cfg: dict | None = None, chat: QWidget | None = None,
                  on_quit=None) -> SettingsPage:
    """开一张设置窗（不阻塞调用方）。chat 给了就当「对话」那一页用。

    on_quit 给了，「关于」页底部就有一颗「退出鲸屿」（2026-11-27 补，治「关不掉」）。
    """
    win = SettingsPage(cfg, chat=chat, on_quit=on_quit)
    win.setAttribute(Qt.WA_DeleteOnClose, True)
    win.show()
    win.raise_()
    win.activateWindow()

    if getattr(win, "_reveal_pending", False):
        def _reveal() -> None:
            try:
                win.setWindowOpacity(1.0)
                win._reveal_pending = False
            except RuntimeError:                        # 已经关掉了
                pass
        QTimer.singleShot(110, _reveal)                 # 兜底：到点无论如何显出来
    return win


# ---------------------------------------------------------------- 插件页的小零件
def _plug_chip(info: dict, size: int = 34) -> QWidget:
    """插件那一行左边的小方块：插件自己写 ICON 就用它，没写就取名字头一个字。

    为什么不用图片：插件只有一个 .py，想带图就得带一堆文件；一个字加个底色，
    一眼能认出是谁，也省得为了一张图就多出个目录。
    """
    text = (info.get("icon") or (info.get("name") or info.get("id") or "?")[:1])[:2]
    lab = QLabel(text)
    lab.setFixedSize(size, size)
    lab.setAlignment(Qt.AlignCenter)
    hue = sum(ord(c) for c in str(info.get("id") or "?")) % 4
    bg = ["#eaf1ff", "#e8f8f2", "#fdf1e6", "#f2ecff"][hue]
    fg = ["#4d7cfe", "#2f9e6b", "#c47a2c", "#7b5bd6"][hue]
    lab.setStyleSheet(
        "background:%s;color:%s;border-radius:9px;font-size:%dpx;font-weight:600;"
        % (bg, fg, 15 if len(text) > 1 else 16)
    )
    return lab


class _PlugSettingsDialog(QDialog):
    """按 `SETTINGS` 声明长出来的小表单。插件加一项，页面这里不用改。"""

    def __init__(self, parent, title: str, schema: list[dict], values: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} · 设置")
        self.setMinimumWidth(420)
        self._fields: dict[str, object] = {}
        self._schema = schema

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)

        form = QVBoxLayout()
        form.setSpacing(8)
        for item in schema:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            kind = str(item.get("kind") or "text")
            label = QLabel(str(item.get("label") or key))
            label.setObjectName("h2")
            form.addWidget(label)
            val = values.get(key)
            if kind == "bool":
                w = QCheckBox("开")
                w.setChecked(bool(val))
            elif kind == "lines":
                w = QPlainTextEdit()
                w.setFixedHeight(76)
                items = val if isinstance(val, (list, tuple)) else []
                w.setPlainText("\n".join(str(x) for x in items))
            elif kind == "int":
                w = QSpinBox()
                w.setRange(0, 65535)
                try:
                    w.setValue(int(val if val is not None else 0))
                except (TypeError, ValueError):
                    w.setValue(0)
            else:
                w = QLineEdit("" if val is None else str(val))
            self._fields[key] = w
            form.addWidget(w)
            hint = str(item.get("hint") or "")
            if hint:
                tip = QLabel(hint)
                tip.setObjectName("soft")
                tip.setWordWrap(True)
                form.addWidget(tip)
        outer.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = _ghost("算了")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = _primary("存下来")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        outer.addLayout(row)

    def values(self) -> dict:
        out: dict = {}
        for item in self._schema:
            key = str(item.get("key") or "").strip()
            w = self._fields.get(key)
            if not w:
                continue
            kind = str(item.get("kind") or "text")
            if kind == "bool":
                out[key] = bool(w.isChecked())
            elif kind == "lines":
                lines = [ln.strip() for ln in w.toPlainText().splitlines() if ln.strip()]
                out[key] = lines
            elif kind == "int":
                out[key] = int(w.value())
            else:
                out[key] = w.text().strip()
        return out


# ---------------------------------------------------------------- 自己跑起来
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import appicon
    app.setWindowIcon(appicon.icon())
    w = show_settings()
    raise SystemExit(app.exec())
