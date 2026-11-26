"""问一句：要动电脑的时候，从应用里冒一张小卡片，问「做吗」。

2026-11-21 月下：「权限还是弹窗，不是对话框」「人家这个挺好的，就用对话框来解决」。
所以不再开独立 QDialog，而是把卡片做成**当前应用窗口的子控件**（设置窗或身体窗），
像 Coop 的 ask 气泡一样贴在应用里；后台线程仍然用事件循环等一个答案。

为什么不用 QMessageBox：
  1. 它跟这个家不是一个样子——弹出来像杀毒软件。
  2. **更要紧的**：问是在后台线程里发生的（`llm.talk` 跑在工作线程），
     那儿弹窗等于在非 GUI 线程里开事件循环，Windows 上轻则卡住，重则崩。
所以这里：工作线程 → 发信号 → 主线程把卡片挂到应用窗上 → 工作线程等结果。

回 False 就是「不做」，闸门那边会直接把话回给人，不留痕。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QObject, Signal, QEventLoop, QEvent, QTimer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

INK = "#283246"
SOFT = "#8a97ab"
OK = "#3f7dd8"


class AskCard(QFrame):
    """一张小卡片：一句问话 + 做 / 不做。挂在应用窗口里，不是独立窗体。"""

    def __init__(self, question: str, near=None) -> None:
        parent = self._pick_parent(near)
        super().__init__(parent)
        self._parent_widget = parent
        self._answer = False
        self._loop = QEventLoop(self)
        self._guard = QTimer(self)
        self._guard.setInterval(400)
        self._guard.timeout.connect(self._check_parent)
        if parent is not None:
            parent.installEventFilter(self)
        self.setObjectName("ask-card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "#ask-card{background:white;border:1px solid #d8dfe8;border-radius:14px;}")

        card = QVBoxLayout(self)
        card.setContentsMargins(18, 14, 18, 12)
        card.setSpacing(10)

        text = QLabel(question)
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{INK}; font-family:'Microsoft YaHei'; font-size:13px;"
                           "background:transparent;")
        card.addWidget(text)

        row = QHBoxLayout()
        row.addStretch(1)
        import i18n
        no = QPushButton(i18n.t("page.perm.ask.no"))
        yes = QPushButton(i18n.t("page.perm.ask.yes"))
        for b, primary in ((no, False), (yes, True)):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            b.setMinimumWidth(64)
            if primary:
                b.setStyleSheet(
                    f"QPushButton{{background:{OK};color:white;border:none;border-radius:8px;"
                    f"font-family:'Microsoft YaHei';font-size:12px;}}"
                    f"QPushButton:hover{{background:#336cb8;}}")
            else:
                b.setStyleSheet(
                    "QPushButton{background:#eef1f5;color:#566173;border:none;border-radius:8px;"
                    "font-family:'Microsoft YaHei';font-size:12px;}"
                    "QPushButton:hover{background:#e2e7ee;}")
        no.clicked.connect(lambda: self._finish(False))
        yes.clicked.connect(lambda: self._finish(True))
        row.addWidget(no)
        row.addWidget(yes)
        card.addLayout(row)

        self.adjustSize()
        width = 340
        if parent is not None:
            width = max(260, min(width, parent.width() - 24))
        self.setFixedWidth(width)
        self.adjustSize()
        if parent is not None:
            x = max(8, (parent.width() - self.width()) // 2)
            y = max(12, min(parent.height() - self.height() - 12,
                            int(parent.height() * 0.10)))
            self.move(x, y)
        else:
            # 没有任何可见的应用窗：卡片自己就是那个「真的看得见的小窗」。
            self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.adjustSize()
            scr = QApplication.primaryScreen().availableGeometry()
            self.move(scr.center().x() - self.width() // 2,
                      scr.center().y() - self.height() // 2)
        self.hide()

    @staticmethod
    def _pick_parent(near):
        """只认真的看得见的窗口；设置窗关了/收起来就退回身体窗，再没有就用顶层小窗。"""
        for cand in (QApplication.activeWindow(), near):
            try:
                if cand is not None and cand.isVisible() \
                        and cand.width() >= 260 and cand.height() >= 200:
                    return cand
            except Exception:                        # noqa: BLE001
                pass
        return None

    def _to_top(self, why: str) -> None:
        """父窗不可见/被关掉：把卡片摘出来，变成真的看得见的小窗，别死等。"""
        if self._parent_widget is None:
            return
        parent = self._parent_widget
        try:
            parent.removeEventFilter(self)
        except Exception:                            # noqa: BLE001
            pass
        self._parent_widget = None
        try:
            self.setParent(None)
            self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.adjustSize()
            scr = QApplication.primaryScreen().availableGeometry()
            self.move(scr.center().x() - self.width() // 2,
                      scr.center().y() - self.height() // 2)
            self.show()
            self.raise_()
        except Exception:                            # noqa: BLE001
            pass
        try:
            import memory
            memory.note_file("perm.log", f"ask-fallback: {why}")
        except Exception:                            # noqa: BLE001
            pass

    def _check_parent(self) -> None:
        if self._parent_widget is not None and not self._parent_widget.isVisible():
            self._to_top("parent-hidden")

    def eventFilter(self, obj, ev):              # noqa: N802
        if obj is self._parent_widget and ev.type() in (QEvent.Close, QEvent.Hide):
            self._to_top("parent-hide-event")
        return False

    def _finish(self, ok: bool) -> None:
        self._answer = bool(ok)
        self._guard.stop()
        self.hide()
        self._loop.quit()

    def ask(self) -> bool:
        """显示并等一次回答；父窗不可见时自动切成真正可见的小窗。"""
        self._guard.start()
        self.show()
        self.raise_()
        self.setFocus()
        self._loop.exec()
        self._guard.stop()
        self.deleteLater()
        return self._answer

    def keyPressEvent(self, event) -> None:      # Esc = 不做，回车 = 做
        if event.key() == Qt.Key_Escape:
            self._finish(False)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._finish(True)
        else:
            super().keyPressEvent(event)


class Asker(QObject):
    """闸门要的 `ask(question) -> bool`。任何线程都能叫，答完就回。"""

    request = Signal(str)

    def __init__(self, near_getter=None, timeout: float = 300.0) -> None:
        super().__init__()
        self._near = near_getter          # 回一个 QWidget，卡片贴着它弹
        self._timeout = timeout
        self._ev = threading.Event()
        self._answer = False
        self.request.connect(self._show)  # 队列连接：一定在主线程里跑

    def _show(self, question: str) -> None:
        try:
            near = self._near() if callable(self._near) else None
            card = AskCard(question, near)
            self._answer = card.ask()
        except Exception:
            self._answer = False
        finally:
            self._ev.set()

    def ask(self, question: str) -> bool:
        self._ev.clear()
        self._answer = False
        self.request.emit(question)
        # 人不理它，就当不做——宁可什么都不动，也不自己替人答应
        if not self._ev.wait(self._timeout):
            # 人不理它，就当不做；把原因写进 perm.log，别让闸门那边像「死等」
            try:
                import memory
                memory.note_file("perm.log", f"ask-timeout: {question[:120]}")
            except Exception:                        # noqa: BLE001
                pass
            return False
        return bool(self._answer)
