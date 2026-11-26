"""页面：新房子自己的「对话页」，照着 Coop 那个页面的样子做。

长这样（从上到下）：
  顶栏     「对话」+ 一个小圆点（在不在）+ 右边「收起」
  时间线   他的话靠右、灰底气泡；我的话靠左、带小头像的白气泡；
           气泡下面一行极小的灰字，写这条是怎么出来的（说过 / 出声 / 想过）
           中间插一行小字「操作电脑 · 2 步」那种进度条也照做
  提问卡   问题 + 几个选项按钮 + 自己写一格
  底栏     输入框 + 图片按钮 + 发送

怎么开：右键身体（或 `main.py` 里 page.show_page）。
"""
from __future__ import annotations

import os
import re
import threading

from PySide6.QtCore import Qt, QObject, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import llm
import memory

BG = "#ffffff"
INK = "#283246"


def _squash(text: str) -> str:
    """比一句话是不是同一句：去掉所有空白再比（换行、缩进不算区别）。"""
    return "".join(str(text or "").split())
SOFT = "#8a97ab"
MINE = "#eef3fb"       # 我的头像底色
THEIRS = "#f1f2f4"     # 他的气泡

_MOOD_RE = re.compile(r"【([^】]{1,8})】")
_MARK_RE = re.compile(r"【[^】]*】|<[^>]*>")


class _Bridge(QObject):
    got = Signal(str)
    status = Signal(str)


# ---------------------------------------------------------------- 小零件
def _round(w: QWidget, css: str) -> QWidget:
    w.setStyleSheet(css)
    return w


class Bubble(QFrame):
    """一个气泡。side='left' 是我说的，'right' 是他说的。"""

    def __init__(self, side: str, text: str, caption: str = "", avatar: QPixmap | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.setObjectName("bubble")
        mine = side == "left"
        color, ink = ("#ffffff", INK) if mine else (THEIRS, INK)
        border = "1px solid #e3e9f2" if mine else "none"
        self.setStyleSheet(
            f"#bubble{{background:{color};border:{border};border-radius:12px;}}"
        )
        self.setMaximumWidth(330)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)

        inner = QVBoxLayout(self)
        inner.setContentsMargins(12, 9, 12, 9)
        inner.setSpacing(3)

        body = QLabel(text, self)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(f"color:{ink};font-size:13px;background:transparent;")
        inner.addWidget(body)

        # 11-21 18:34 抓到的白框：这里原先是 `QLabel(caption)`，**没有父**。
        # `setVisible(True)` 一叫，Qt 就把它当成顶层窗建出来、映射到屏幕上——
        # 于是每铺一个气泡就闪一个带原生标题栏的空框（实测 135×51，
        # 一秒 25 个，整页历史铺完闪三秒多）。父传进去，它就只是子控件。
        self.caption = QLabel(caption, self)
        self.caption.setStyleSheet(f"color:{SOFT};font-size:10px;background:transparent;")
        self.caption.setVisible(bool(caption))
        inner.addWidget(self.caption)

    def add_image(self, path: str) -> None:
        pix = QPixmap(path)
        if pix.isNull():
            return
        lab = QLabel()
        lab.setPixmap(pix.scaledToWidth(min(280, pix.width()), Qt.SmoothTransformation))
        lab.setStyleSheet("background:transparent;")
        self.layout().addWidget(lab)


class _Avatar(QLabel):
    def __init__(self, pix: QPixmap | None) -> None:
        super().__init__()
        self.setFixedSize(26, 26)
        if pix is not None and not pix.isNull():
            self.setPixmap(pix.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.setText("鱼")
            self.setAlignment(Qt.AlignCenter)
            self.setStyleSheet(
                f"background:{MINE};border-radius:13px;color:#4a7ac0;font-size:12px;")
            return
        self.setStyleSheet(f"background:{MINE};border-radius:13px;")


class ToolLine(QLabel):
    """时间线里插的那行小字：『操作电脑 · 2 步  切换窗口』。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(f"color:{SOFT};font-size:11px;padding:2px 4px;")


class AskCard(QFrame):
    """提问卡：问题 + 选项 + 自己写一格。"""

    def __init__(self, question: str, options: list[str], on_pick,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ask")
        self.setStyleSheet(
            "#ask{background:#ffffff;border:1px solid #e3e9f2;border-radius:12px;}")
        self.setMaximumWidth(330)
        self._on_pick = on_pick

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        q = QLabel(question)
        q.setWordWrap(True)
        q.setStyleSheet(f"color:{INK};font-size:13px;background:transparent;")
        lay.addWidget(q)

        for opt in options:
            btn = QPushButton(opt)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{text-align:left;background:#f7fafe;border:1px solid #dbe5f3;"
                "border-radius:9px;padding:7px 10px;font-size:12px;color:#3d5680;}"
                "QPushButton:hover{background:#eaf1fc;border-color:#9dc0ee;}")
            btn.clicked.connect(lambda _=False, o=opt: self._pick(o))
            lay.addWidget(btn)

        row = QHBoxLayout()
        self.own = QLineEdit()
        self.own.setPlaceholderText("自行回答")
        self.own.setStyleSheet(
            "QLineEdit{border:1px solid #dbe5f3;border-radius:9px;padding:6px 8px;font-size:12px;}")
        self.own.returnPressed.connect(lambda: self._pick(self.own.text().strip()))
        go = QPushButton("发送")
        go.setStyleSheet(
            "QPushButton{background:#78aaeb;color:white;border:none;border-radius:9px;"
            "padding:6px 12px;font-size:12px;}")
        go.clicked.connect(lambda: self._pick(self.own.text().strip()))
        row.addWidget(self.own, 1)
        row.addWidget(go)
        lay.addLayout(row)

    def _pick(self, text: str) -> None:
        if not text:
            return
        self.setEnabled(False)
        self._on_pick(text)


# ---------------------------------------------------------------- 页面
class ChatPage(QWidget):
    # 11-03 15:05：让我能在页面上问一句（工作线程 emit，主线程弹卡，答案塞回工具回执）
    ask_request = Signal(str, list, object)

    def __init__(self, cfg: dict, say, history: list | None = None, status=None,
                 embedded: bool = False, said=None) -> None:
        super().__init__()
        self.cfg = cfg
        self._say = say
        self._said = said
        self._status = status
        self.history = history if history is not None else []
        if history is None:
            # 3-3：没传历史时自己从会话文件读，别让对话页从空白开始。
            try:
                import session
                self.history = session.load(cfg, "main", limit=40)
            except Exception:                    # noqa: BLE001
                self.history = []
        self.body = None          # 3-4：main 把身体接进来，做动作用（可以没有）
        self.embedded = embedded          # True：塞进设置页里当一页，不自己开窗
        # 2026-11-21：选好的图先攒着，等下一次「发」的时候跟文字一起交给模型。
        # 以前这里只写一行「[发了一张图：name]」文本，图本身没进 messages。
        self._pending_images: list[str] = []
        self._tools: list[str] = []       # 这一轮调过的工具，回答完折成一行小字
        self._local_shown: list[str] = [] # 页面上已经自己画过的句子（sync 认出来别画第二遍）

        self.setWindowTitle("鱼鱼的新家 · " + __import__("i18n").t("page.chat.title"))
        if not embedded:
            self.resize(520, 640)

        self._avatar_pix = QPixmap(str(cfg.get("figure_image", ""))) if cfg.get("figure_image") else None

        # 顶栏
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color:#3ec27a;font-size:11px;")
        title = QLabel(__import__("i18n").t("page.chat.title"))
        title.setStyleSheet(f"color:{INK};font-size:16px;font-weight:600;")
        self.status = QLabel("在底边上")
        self.status.setStyleSheet(f"color:{SOFT};font-size:11px;")
        fold = QPushButton("收起")
        fold.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{SOFT};font-size:12px;}}"
            "QPushButton:hover{color:#4a7ac0;}")
        fold.clicked.connect(self.hide)

        gear = QPushButton("⚙")
        gear.setToolTip("设置")
        gear.setCursor(Qt.PointingHandCursor)
        gear.setStyleSheet(
            "QPushButton{border:none;background:transparent;color:#7f8ca1;font-size:14px;}"
            "QPushButton:hover{color:#4a7ac0;}")
        gear.clicked.connect(self._open_settings)
        self.on_settings = None               # main.py 里挂上真正的开窗函数
        self.ask_request.connect(self._on_ask_request)

        # 11-04 18:35 修：以前这一页只在 show_page() 里 sync() 一次。
        # 嵌在设置页里（embedded=True）从来不走 show_page，所以她的回答明明写进了
        # chat.log，页面上就是不出现，「在等待 25 秒」也冻着——看着像卡死。
        # 改成每秒补一次新行，只在看得见的时候读文件。
        self._sync_tick = QTimer(self)
        self._sync_tick.setInterval(1000)
        self._sync_tick.timeout.connect(self._sync_if_visible)
        self._sync_tick.start()
        self.gear = gear
        self.fold = fold
        if embedded:
            # 嵌在设置页里：没有「收起」和「⚙」，整页就是设置的一部分
            fold.hide()
            gear.hide()

        top = QHBoxLayout()
        top.addWidget(self.dot)
        top.addWidget(title)
        top.addSpacing(6)
        top.addWidget(self.status)
        top.addStretch(1)
        top.addWidget(gear)
        top.addWidget(fold)

        # 时间线
        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(8)
        self.rows.addStretch(1)
        holder = QWidget()
        holder.setLayout(self.rows)
        holder.setStyleSheet(f"background:{BG};")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(holder)
        self.scroll.setStyleSheet(f"QScrollArea{{background:{BG};}}")

        # 底栏
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("给 鱼鱼 发消息…")
        self.edit.setStyleSheet(
            "QLineEdit{border:1px solid #dce4f0;border-radius:10px;padding:8px 10px;"
            f"font-size:13px;color:{INK};background:#fbfcfe;}}")
        self.edit.returnPressed.connect(self._submit)

        clip = QPushButton("图")
        clip.setToolTip("发一张图")
        clip.setStyleSheet(
            "QPushButton{border:none;background:transparent;font-size:15px;color:#7f8ca1;}")
        clip.clicked.connect(self._pick_image)

        self.send = QPushButton("发")
        self.send.setStyleSheet(
            "QPushButton{background:#78aaeb;color:white;border:none;border-radius:10px;"
            "padding:8px 16px;font-size:13px;} QPushButton:hover{background:#5f97de;}")
        self.send.clicked.connect(self._submit)

        bottom = QHBoxLayout()
        bottom.addWidget(clip)
        bottom.addWidget(self.edit, 1)
        bottom.addWidget(self.send)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addWidget(self.scroll, 1)
        lay.addLayout(bottom)

        self._bridge = _Bridge()
        self._bridge.got.connect(self._on_reply)
        self._bridge.status.connect(self._on_status)
        # 历史气泡等第一次真正显示聊天页再铺：启动时设置页停在「开始」，
        # 这里先建 100 个不可见顶层小窗会闪一片（2026-11-21 双击黑框）。
        self._loaded = False

        # 11-21 18:42 他说「重启完还是不在最下面」：定两次时沉底不够——
        # 气泡折行、行高要等布局跑完才定下来，rangeChanged 之后还会再来几回。
        # 改成「粘在底部」：范围一变就再沉一次；他自己往上翻，就不再粘。
        self._stick = True
        _bar = self.scroll.verticalScrollBar()
        _bar.rangeChanged.connect(self._on_range)
        _bar.valueChanged.connect(self._on_scroll)

    def showEvent(self, event) -> None:             # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()
        # 每次切回对话页都沉到底（11-21 18:26 他说的那条）
        self._to_bottom()

    # ---------- 时间线 ----------
    def _add(self, widget: QWidget, side: str) -> None:
        row = QWidget(self)
        row.setAttribute(Qt.WA_DontShowOnScreen, True)
        row.setStyleSheet("background:transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(6)
        if side == "left":
            h.addWidget(_Avatar(self._avatar_pix), 0, Qt.AlignTop)
            h.addWidget(widget, 0, Qt.AlignTop)
            h.addStretch(1)
        elif side == "right":
            h.addStretch(1)
            h.addWidget(widget, 0, Qt.AlignTop)
        else:
            h.addWidget(widget, 0, Qt.AlignHCenter)
            h.addStretch(1)
        self.rows.insertWidget(self.rows.count() - 1, row)
        self._to_bottom()

    def _to_bottom(self) -> None:
        """沉到底。

        11-21 18:26 月下：「他谈到对话页，它是自动在最上一面，它应该是自动在最下面才对。」
        以前是加完控件立刻 setValue(bar.maximum())——那一瞬间 QVBoxLayout 还没算完，
        maximum() 还是旧值，等于没沉；等布局算完又没人再推一把，就停在最上面。
        现在分两下：下一轮事件循环沉一次，60 毫秒后再补一次（气泡折行会再撑高一点）。
        """
        bar = self.scroll.verticalScrollBar()
        self._stick = True

        def _go() -> None:
            bar.setValue(bar.maximum())

        QTimer.singleShot(0, _go)
        QTimer.singleShot(60, _go)

    def _on_range(self, _lo: int, _hi: int) -> None:
        """滚动范围又变了（气泡折行撑高、图加载完）——粘着的话再沉一次。"""
        if not getattr(self, "_stick", True):
            return
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _on_scroll(self, value: int) -> None:
        """他自己往上翻了就不再粘；翻回底部又粘上。"""
        bar = self.scroll.verticalScrollBar()
        self._stick = value >= bar.maximum() - 4

    def add_mine(self, text: str, caption: str = "") -> None:
        self._add(Bubble("left", text, caption, self._avatar_pix, parent=self), "left")

    def add_theirs(self, text: str, source: str = "") -> None:
        self._add(Bubble("right", text, source, parent=self), "right")

    def add_tool_line(self, text: str) -> None:
        self._add(ToolLine(text, parent=self), "center")

    def ask(self, question: str, options: list[str], on_pick) -> None:
        self._add(AskCard(question, options, on_pick, parent=self), "left")

    # ---------- 给工具用：任何线程都能叫 ----------
    def ask_async(self, question: str, options: list, on_pick) -> None:
        """工作线程里调这个：信号排队回到 GUI 线程，卡片才弹得出来。"""
        self.ask_request.emit(str(question), list(options or []), on_pick)

    def _on_ask_request(self, question: str, options: list, on_pick) -> None:
        self.ask(question, options, on_pick)

    # ---------- 读 chat.log ----------
    def _read_log(self) -> list[str]:
        try:
            path = memory.data_dir(self.cfg) / "chat.log"
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def _restore_from_session(self) -> None:
        """chat.log 没了的时候，拿会话文件把最近几句话铺回这一页。

        平时这一页是从 chat.log 重建的；只有日志被清掉、或换机器时才会走到这里，
        免得重启后打开是空白、以为没存上。
        图片那条存的是 [发了一张图：x] 这种内部标记，铺的时候只显示「（图）」，
        不把标记原样露出来。
        """
        try:
            import session
            msgs = session.load(self.cfg, "main", limit=40)
        except Exception:                        # noqa: BLE001
            return
        for m in msgs:
            text = str(m.get("content") or "").strip()
            if not text:
                continue
            if text.startswith("[发了一张图：") and text.endswith("]"):
                self.add_mine("（图）", "图片")
            elif m.get("role") == "user":
                self.add_mine(text, "对话页")
            else:
                self.add_theirs(text)
        self._refresh_head()
        self._to_bottom()

    def reload(self) -> None:
        self._loaded = True
        for i in reversed(range(self.rows.count() - 1)):
            w = self.rows.itemAt(i).widget()
            if w:
                w.deleteLater()
        lines = self._read_log()
        self._shown = 0
        if not lines:
            # 3-3：chat.log 空着时用会话文件补，别让页面空着。
            self._restore_from_session()
        self._append_lines(lines)
        self._refresh_head()
        self._to_bottom()

    def _sync_if_visible(self) -> None:
        """每一秒看一眼：看得见就补新行（嵌在设置页里也能即时看到她的回答）。"""
        if self.isVisible():
            self.sync()

    def sync(self) -> None:
        """只补新行：从输入框或说话键来的那句也出现在这一页上，但不动已经画好的。"""
        lines = self._read_log()
        if len(lines) <= self._shown:
            return
        self._append_lines(lines[self._shown:])
        self._refresh_head()
        self._to_bottom()

    def _mark_local(self, text: str) -> None:
        """这句我先在页面上画出来了，chat.log 里紧接着也会出现同一条。"""
        self._local_shown.append(_squash(text))
        del self._local_shown[:-8]          # 只留最近几条，免得配不上时越堆越多

    def _take_local(self, text: str) -> bool:
        """从 chat.log 读到一条：要是刚才是自己画的，认出来、跳过，不画第二遍。"""
        key = _squash(text)
        for i, t in enumerate(self._local_shown):
            if t == key:
                del self._local_shown[i]
                return True
        return False

    def _append_lines(self, lines: list[str]) -> None:
        last_mine: Bubble | None = None
        swallow = False                  # 上一句是我自己画的，它底下那行「· 说过」也跳过
        for line in lines:
            self._shown += 1
            if line.startswith("["):                 # [时间] 月下: ...
                head, _, rest = line.partition("] ")
                who, _, said = rest.partition(": ")
                if not said:
                    continue
                if who.endswith("月下") or who.endswith("他") or "月下" in who:
                    if self._take_local(said):
                        last_mine = None
                        continue
                    # 来源标签（照 Coop 对话页）：说话键打的那行记的是「月下(说)」
                    # 3-4：从 chat.log 重铺时也把【…】/<…> 剥掉，别让标记漏进气泡。
                    self.add_theirs(_MARK_RE.sub("", said).strip() or said,
                                    "语音" if "说" in who else "对话页")
                    last_mine = None
                else:
                    if self._take_local(said):
                        last_mine = None
                        swallow = True
                        continue
                    last_mine = Bubble("left", _MARK_RE.sub("", said).strip() or said, "",
                           self._avatar_pix, parent=self)
                    self._add(last_mine, "left")
            elif line.startswith("·"):               # · 说过 · 出声（挂在上一句我下面）
                if swallow:
                    swallow = False
                    continue
                cap = line.lstrip("· ").strip()
                if last_mine is not None:
                    last_mine.caption.setText(cap)
                    last_mine.caption.setVisible(True)
                    last_mine = None
                else:
                    self.add_tool_line(cap)
        self._refresh_head()
        self._to_bottom()

    def _refresh_head(self) -> None:
        try:
            head = memory.state_headline(self.cfg) or "（STATE 里没写）"
            self.status.setText(head.splitlines()[0][:28])
        except Exception:
            self.status.setText("在底边上")

    def _open_settings(self) -> None:
        """右上角那个齿轮：开设置窗（main.py 里挂的 settings_page.show_settings）。"""
        if callable(self.on_settings):
            self.on_settings()

    def show_page(self) -> None:
        self.sync()                 # 上次关着时说的话（输入框、说话键）补上来
        self._refresh_head()
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self._to_bottom()

    # ---------- 一问一答 ----------
    def _submit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self._send(text)

    def _send(self, text: str) -> None:
        memory.note_file("chat.log", f"月下: {text}", self.cfg)
        try:
            memory.log_say(self.cfg, "月下", text)          # 4-4：共享月志
        except Exception:                        # noqa: BLE001
            pass
        if getattr(self, "_said", None):
            try:
                self._said(text)                     # 舞台气泡：人说的话也往上叠
            except Exception:                        # noqa: BLE001
                pass
        self.add_theirs(text)
        self._mark_local(text)
        self.history.append({"role": "user", "content": text})
        try:
            import session
            session.append(self.cfg, "main", "user", text, source="typed", entry="page")
        except Exception as e:                   # noqa: BLE001
            memory.note_file("tool.log", f"会话没存上：{type(e).__name__} {e}", self.cfg)
        # 4-2：确认草稿要在模型之前处理；模型自己发的「确认 d-xxx」到不了这里。
        try:
            import outbox as _outbox
            _done = _outbox.confirm_if_any(text, "typed")
        except Exception:                        # noqa: BLE001
            _done = None
        if _done:
            self.history.append({"role": "assistant", "content": _done})
            try:
                import session
                session.append(self.cfg, "main", "assistant", _done, entry="page")
            except Exception:                    # noqa: BLE001
                pass
            self.add_mine(_done, "确认")
            self._to_bottom()
            return
        # 2026-11-21：把攒下的图拼成 messages 里的 image_url，跟这句一起交给模型。
        images = []
        for p in self._pending_images:
            try:
                import llm as _llm
                piece = _llm.image_message(p, "（这是月下刚发来的一张图。）")
                if piece:
                    images.append(piece)
            except Exception:                    # noqa: BLE001
                pass
        self._pending_images = []
        threading.Thread(target=self._ask, args=(text, images), daemon=True).start()

    def _ask(self, text: str, images: list[dict] | None = None) -> None:
        import tools as toolmod

        def on_start(name: str, args: dict) -> None:
            try:
                self._bridge.status.emit(toolmod.status_line(name, args))
            except Exception:
                pass

        def on_tool(name: str, args: dict, result: str) -> None:
            self._tools.append(name)

        answer = llm.talk(text, self.history[:-1], self.cfg,
                          source="typed", entry="page",
                          on_start=on_start, on_tool=on_tool, images=images)
        self._bridge.got.emit(answer)

    def _tool_summary(self) -> str:
        """一轮调过的工具折成一行：「工具 · 3 步 · 读 STATE.md」（照 Coop 那行）。"""
        names = self._tools
        self._tools = []
        if not names:
            return ""
        try:
            import tools as toolmod
            last = toolmod.status_line(names[-1], {}).replace("正在", "").strip()
        except Exception:
            last = ""
        head = "操作电脑" if all(n.startswith("cua") for n in names) else "工具"
        return f"{head} · {len(names)} 步" + (f" · {last}" if last else "")

    def _on_status(self, text: str) -> None:
        if callable(self._status):
            try:
                self._status(text, 8.0)
            except Exception:
                pass

    def _on_reply(self, answer: str) -> None:
        answer = (answer or "").strip()
        if not answer:
            return
        self.history.append({"role": "assistant", "content": answer})
        try:
            import session
            session.append(self.cfg, "main", "assistant", answer, entry="page")
        except Exception as e:                   # noqa: BLE001
            memory.note_file("tool.log", f"会话没存上：{type(e).__name__} {e}", self.cfg)
        # 3-3 改：原来这里也是 del self.history[:-12]，和输入框那处一起把旧话截掉；
        # 现在两边都留 40 条，盘上 200 条，喂模型仍只 12 条。
        del self.history[:-40]
        try:
            memory.log_say(self.cfg, "我", answer)          # 4-4：她的回答也进月志
        except Exception:                        # noqa: BLE001
            pass
        # 工具那行：这一轮调过什么，折成「工具 · 3 步 · 读 STATE.md」插在气泡上面
        line = self._tool_summary()
        if line:
            self.add_tool_line(line)
        # 气泡里不显示【表情】<动作> 标记；第一对【】拿来做下面的情绪小字（照 Coop）
        mood = ""
        m = _MOOD_RE.search(answer)
        if m and " " not in m.group(1):
            mood = m.group(1).strip()
        # 3-4：正文里的【…】/<…> 能对上当前包词表就做动作；对不上保留小字并记日志。
        # 正文照旧由 _MARK_RE 剥干净，标记不会漏进气泡。
        try:
            import figure_vocab
            if self.body is not None:
                for wid in figure_vocab.actions_in(answer):
                    self.body.act(wid)
            for raw in figure_vocab.unknown_in(answer):
                memory.note_file("frame.log", f"词表里没有：{raw}", self.cfg)
            if mood and figure_vocab.resolve(mood):
                mood = ""            # 已经做成动作了，就不在气泡上再挂一遍小字
        except Exception:                        # noqa: BLE001
            pass
        shown = _MARK_RE.sub("", answer).strip() or answer
        parts = ["说过"] + (["出声"] if self.cfg.get("speak_aloud") else [])
        if mood:
            parts.append(mood)
        self.add_mine(shown, " · ".join(parts))
        # 日志里记的是没剥标记的原话（main.py 的 say() 记的），所以拿原话去对
        self._mark_local(answer)
        self._say(answer, max(4.0, min(14.0, len(answer) / 9.0)))

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "发一张图", "", "图片 (*.png *.jpg *.jpeg *.gif *.webp)")
        if not path:
            return
        name = os.path.basename(path)
        memory.note_file("chat.log", f"月下: [图] {name} {path}", self.cfg)
        b = Bubble("right", f"[图] {name}", parent=self)
        b.add_image(path)
        self._add(b, "right")
        marker = f"[发了一张图：{name}]"
        self.history.append({"role": "user", "content": marker})
        # 图本身留着，下一次 _send 时交给 llm.talk（历史里仍然只存这行文字标记）。
        self._pending_images.append(path)
        if len(self._pending_images) > 4:
            del self._pending_images[:-4]
        try:
            import session
            session.append(self.cfg, "main", "user", marker, source="typed", entry="page")
        except Exception as e:                   # noqa: BLE001
            memory.note_file("tool.log", f"会话没存上：{type(e).__name__} {e}", self.cfg)

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(ev)
