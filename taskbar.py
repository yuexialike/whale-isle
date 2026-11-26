"""任务栏那一格（11-02 20:07 月下：「任务栏里要有一格，点了能开来」）

鲸屿的本体是一张贴在屏幕底边的窗，带 Qt.Tool，Windows 不给它任务栏按钮——
托盘里能看见，任务栏上永远找不到，月下说的「操控不太好操控」就是这个。

做法：另开一个 1×1 的透明普通窗当「锚」。Windows 看见它就往任务栏加一格；
用户点那一格，锚被激活，我们就把设置页（对话那页）开出来。
锚自己不显示、不吃鼠标、不抢焦点，视觉上什么都不多。
"""
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget


class TaskbarAnchor(QWidget):
    def __init__(self, on_click, title="鲸屿", icon=None, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self._on_click = on_click
        self._busy = False
        self.setWindowTitle(title)
        if icon is not None:
            self.setWindowIcon(icon)
        self.setFixedSize(1, 1)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 开出来的时候别抢前台——不然一启动就被当成「用户点了任务栏」，设置页自己弹出来
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.0)          # 看不见，但 Windows 仍然给任务栏按钮
        scr = QApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            self.move(g.right() - 1, g.bottom() - 1)   # 一定要在屏幕里，别挪到屏幕外
        # 前 1.5 秒的激活都不算数（那只是窗口自己在露面）
        self._armed = False
        QTimer.singleShot(1500, self._arm)

    def _arm(self):
        self._armed = True

    # 点任务栏那一格 → 窗口被激活 → 开设置页
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            if self._armed and not self._busy:
                self._busy = True
                QTimer.singleShot(0, self._fire)

    def _fire(self):
        try:
            self._on_click()
        except Exception:                    # noqa: BLE001 —— 锚绝不能把主程序带崩
            pass
        finally:
            self._busy = False
            # 把激活让回去，免得下次再点就没反应
            QTimer.singleShot(0, self.lower)
