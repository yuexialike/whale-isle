"""自己摆位置看一眼 littlewhale：`python preview_littlewhale2.py --seconds=45 [--spout]`。

figure_web.preview() 把窗贴在屏幕右下角，那条鱼的尾巴会被屏幕边切掉；这里改成摆在左上，
窗大小和位置都能自己给。看完就关，不改 config。
"""
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

import figure_pack
import figure_web


def arg(name, default):
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


if __name__ == "__main__":
    figure_pack.set_current("littlewhale")
    seconds = int(arg("seconds", "45"))
    stage = arg("stage", "560x600").lower().split("x")
    w, h = int(stage[0]), int(stage[1])
    x, y = (int(v) for v in arg("at", "60x60").lower().split("x"))

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    win = QWidget()
    win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    win.setAttribute(Qt.WA_TranslucentBackground, True)
    win.resize(w, h)
    win.move(x, y)
    fig = figure_web.FigureWeb("deepseek-cape", win)
    lay = QVBoxLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(fig)
    fig.set_size(w, h)
    win.show()

    if "--spout" in sys.argv[1:]:
        t = QTimer(fig)
        t.setInterval(4000)

        def spout() -> None:
            if fig.ready:
                fig.do("spout")
        t.timeout.connect(spout)
        t.start()

    def done() -> None:
        print(f"ready={fig.ready} err={fig.error}", flush=True)
        app.quit()
    QTimer.singleShot(seconds * 1000, done)
    raise SystemExit(app.exec())
