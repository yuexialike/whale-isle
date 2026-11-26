"""第一次开机时那一页纸：三步，说完就进屋。

月下 20:08 清单第 7 项：「第一次打开的引导页」。
为什么要它：发给别人的包里只有一个 exe 和一堆积木，对方双击之后会看见一条鱼站在
屏幕底边——他不会知道要先填 key，也不知道它能动电脑、得自己一条条给权限。
设置页里这些都写着，但**没人会先翻设置页**。所以第一次开机摆一页纸：

  ① 给它张嘴 —— 填 API key（留空也行，那就是先不联网说话）；
  ② 让它站哪 —— 屏幕左下 / 正中 / 右下，三选一；
  ③ 它动不了你的电脑 —— 现在一条权限都没给，要用的时候在设置页一条条开。

三条都只有一句话，不挡人：右上角能关，关掉也算看过（写 `welcomed: true`），
以后不再弹。**不覆盖已有的选**——`x_fraction` 有值就按它的来当默认选中。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

import memory

STYLE = """
QDialog { background: #f4f7ff; }
QLabel#title { color: #1c2340; font-size: 18px; font-weight: 600; }
QLabel#sub   { color: #4a5578; font-size: 13px; }
QLabel#step  { color: #1c2340; font-size: 14px; font-weight: 600; }
QLabel#hint  { color: #6b7699; font-size: 12px; }
QLabel#foot  { color: #6b7699; font-size: 12px; }
QFrame#card  { background: #ffffff; border: 1px solid #dfe5f5; border-radius: 12px; }
QLineEdit { background: #fbfcff; border: 1px solid #dfe5f5; border-radius: 9px;
            padding: 8px 10px; font-size: 13px; color: #1c2340; }
QLineEdit:focus { border-color: #4d7cfe; }
QPushButton { background: #e6ecff; color: #3b4a7a; border: 0; border-radius: 9px;
              padding: 8px 16px; font-size: 13px; }
QPushButton:hover { background: #d8e2ff; }
QPushButton#go { background: #4d7cfe; color: #ffffff; font-size: 14px; padding: 9px 20px; }
QPushButton#go:hover { background: #3f6ef0; }
QPushButton#on { background: #4d7cfe; color: #ffffff; }
"""

SPOTS = [("左边", 0.18), ("正中", 0.5), ("右边", 0.82)]


def _card() -> tuple[QWidget, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    box = QVBoxLayout(f)
    box.setContentsMargins(16, 13, 16, 13)
    box.setSpacing(7)
    return f, box


class WelcomeWindow(QDialog):
    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("鲸屿 · 第一次见面")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(470)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        title = QLabel("先认识一下，三条")
        title.setObjectName("title")
        sub = QLabel("都是小事，看完就进去；以后想改，都在「设置」里。")
        sub.setObjectName("sub")
        sub.setWordWrap(True)

        # ① key
        c1, b1 = _card()
        t1 = QLabel("① 给它一张嘴")
        t1.setObjectName("step")
        h1 = QLabel("填 DeepSeek 的 API key，它才能真说话。现在不填也行，"
                    "以后在设置 › 模型里补。")
        h1.setObjectName("hint")
        h1.setWordWrap(True)
        self.key = QLineEdit(str(cfg.get("api_key") or ""))
        self.key.setPlaceholderText("sk-…（可以留空）")
        self.key.setEchoMode(QLineEdit.Password)
        b1.addWidget(t1)
        b1.addWidget(h1)
        b1.addWidget(self.key)

        # ② 站哪
        c2, b2 = _card()
        t2 = QLabel("② 让它站在哪儿")
        t2.setObjectName("step")
        h2 = QLabel("站在屏幕底边。不喜欢拖一下也行，这里只是先挑个位置。")
        h2.setObjectName("hint")
        h2.setWordWrap(True)
        row = QHBoxLayout()
        self.spot_btns: list[QPushButton] = []
        cur = float(cfg.get("x_fraction", 0.5) or 0.5)
        self.pick = min(SPOTS, key=lambda s: abs(s[1] - cur))[1]
        for label, x in SPOTS:
            btn = QPushButton(label)
            btn.setObjectName("on" if abs(x - self.pick) < 1e-6 else "")
            btn.clicked.connect(lambda _=False, xx=x: self.choose(xx))
            row.addWidget(btn)
            self.spot_btns.append(btn)
        b2.addWidget(t2)
        b2.addWidget(h2)
        b2.addLayout(row)

        # ③ 权限
        c3, b3 = _card()
        t3 = QLabel("③ 它动不了你的电脑")
        t3.setObjectName("step")
        h3 = QLabel("一条权限都没开：看不见屏幕、动不了鼠标键盘、也不会自己发消息。"
                    "哪天真要它帮忙，再去设置 › 权限里一条条给——给哪条就是哪条。")
        h3.setObjectName("hint")
        h3.setWordWrap(True)
        b3.addWidget(t3)
        b3.addWidget(h3)

        foot = QLabel("可以随时关，关了就当看过了。")
        foot.setObjectName("foot")

        go = QPushButton("好了，进去吧")
        go.setObjectName("go")
        go.clicked.connect(self.finish)

        buttons = QHBoxLayout()
        buttons.addWidget(foot)
        buttons.addStretch(1)
        buttons.addWidget(go)

        box = QVBoxLayout(self)
        box.setContentsMargins(22, 20, 22, 18)
        box.setSpacing(11)
        box.addWidget(title)
        box.addWidget(sub)
        box.addWidget(c1)
        box.addWidget(c2)
        box.addWidget(c3)
        box.addLayout(buttons)

    def choose(self, x: float) -> None:
        self.pick = x
        for btn, (_label, xx) in zip(self.spot_btns, SPOTS):
            btn.setObjectName("on" if abs(xx - x) < 1e-6 else "")
            btn.style().unpolish(btn)      # 换了 objectName 得让 Qt 重画一遍
            btn.style().polish(btn)

    def _save(self, **changes) -> None:
        """只把改到的几项盖进真的 config.json。

        20:22 修：以前是把整个 `self.cfg` 存回去——正常路径没事（传进来的本来就是
        `memory.load_config()`），可要是有人拿一份**半截配置**开这个窗（比如 my 的试看脚本），
        关一下就把真的 config.json 冲掉了。所以先读一遍真的，只盖这几项。
        """
        self.cfg.update(changes)
        try:
            real = memory.load_config()
        except Exception:                                   # noqa: BLE001
            real = dict(self.cfg)
        real.update(changes)
        try:
            memory.save_config(real)
        except OSError as exc:
            memory.note_file("startup.log", f"引导页存不下配置：{exc}")

    def finish(self) -> None:
        changes = {"x_fraction": self.pick, "welcomed": True}
        key = self.key.text().strip()
        if key:                                  # 留空 = 不动原来的 key
            changes["api_key"] = key
        self._save(**changes)
        self.accept()

    def closeEvent(self, ev) -> None:      # 右上角关掉 = 也算看过了
        if not self.cfg.get("welcomed"):
            self._save(welcomed=True)
        super().closeEvent(ev)


def needed(cfg: dict) -> bool:
    """要不要弹这一页。

    只认一个记号：配置里有没有 `welcomed` 这个键。
      · 新装的包：`firstrun` 写进去 `welcomed: false` → 弹，看完变 true，以后不弹；
      · 老配置（引导页做出来之前的，比如我们自己这台）：压根没这个键
        → 补一个 true，不打扰人。
    用「键在不在」而不是「key 填没填」当判据，是因为默认配置里 `api_key_env`
    本来就有值，拿它判断的话新装的包会一次都不弹。
    """
    if "welcomed" in cfg:
        return not bool(cfg.get("welcomed"))
    cfg["welcomed"] = True
    try:
        real = memory.load_config()
        real["welcomed"] = True
        memory.save_config(real)
    except OSError:
        pass
    return False


# 20:35 补的别名：`main.py` 里有两处等着老接口——一处 `show_welcome(cfg)`，
# 一处 `should_show(cfg)` + `run_onboarding(cfg, anchor, say)`。
# 我当时只写了前者，启动日志里就天天刷「引导页没开起来：no attribute 'should_show'」。
# 两个名字都留着，指的是同一页纸；用 `_ONCE` 挡住别弹两次。
_ONCE = {"shown": False}

should_show = needed


def run_onboarding(cfg: dict, anchor=None, say=None) -> WelcomeWindow | None:  # noqa: ARG001
    return show_welcome(cfg)


def show_welcome(cfg: dict) -> WelcomeWindow | None:
    """开一页纸（不阻塞）。不需要弹就返回 None。"""
    if _ONCE["shown"] or not needed(cfg):
        return None
    _ONCE["shown"] = True
    win = WelcomeWindow(cfg)
    win.setAttribute(Qt.WA_DeleteOnClose, True)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


if __name__ == "__main__":             # 自己看这张窗：python welcome.py
    import sys
    app = QApplication(sys.argv)
    show_welcome(memory.load_config())
    sys.exit(app.exec())
