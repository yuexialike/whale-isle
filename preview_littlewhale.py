"""只用来看一眼 littlewhale 这个包：`python preview_littlewhale.py --seconds=25 [--spout]`。

figure_web.preview() 用的是 figure_pack.current()，所以在开窗前把它指到 littlewhale。
带 --spout 时每 4 秒喷一次水（这个包的核心动作，别处不好触发）。
看完就关，不改 config。
"""
import sys

import figure_pack
import figure_web

if __name__ == "__main__":
    figure_pack.set_current("littlewhale")
    if "--spout" in sys.argv:
        from PySide6.QtCore import QTimer

        base = figure_web.FigureWeb

        class Patched(base):                            # noqa: D101 - 只为加一个定时器
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self._spout = QTimer(self)
                self._spout.setInterval(4000)
                self._spout.timeout.connect(lambda: self.do("spout"))
                self._spout.start()

        figure_web.FigureWeb = Patched
        sys.argv = [a for a in sys.argv if a != "--spout"]
    raise SystemExit(figure_web.preview())
