"""嘴和耳朵的最小版：一个输入框，回车发出去，回答冒气泡。

- 输入框：无边框小条，双击身体时在身体上方弹出来；Esc 收起。
- 说话：起一个线程去问 DeepSeek，回来用 Qt signal 送回主线程冒气泡（不能在工作线程里画界面）。
- 记忆：每来一句就追加到 data/chat.log，同时记进 history（只带最近几轮）。
- 小字：模型要调工具时，头顶先冒一句「正在读 STATE.md」（照 Coop 的 `pet-status.ts`）。
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import threading

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

import llm
import memory


class _Bridge(QObject):
    """把工作线程的结果送回主线程。"""
    got = Signal(str)
    status = Signal(str)


class InputBox(QWidget):
    def __init__(self, cfg: dict, say, history: list | None = None, status=None,
                 said=None) -> None:
        super().__init__()
        self.cfg = cfg
        self._say = say
        self._said = said
        self._status = status          # 头顶小字：body.status
        if history is None:
            # 3-3：开机先把上次的话读回来；读不出来也不能拦住界面起来。
            try:
                import session
                history = session.load(cfg, "main", limit=40)
            except Exception:                    # noqa: BLE001
                history = []
        self.history = history

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(560, 58)

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("跟我说句话，回车发出去（Esc 收起）")
        self.edit.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,250);border:3px solid #78aaeb;"
            "border-radius:14px;padding:9px 14px;font-size:16px;color:#283246;}"
        )
        self.edit.returnPressed.connect(self._submit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)

        self._bridge = _Bridge()
        self._bridge.got.connect(self._on_reply)
        self._bridge.status.connect(self._on_status)

    # ---------- 开关 ----------
    def pop_up(self, x: int, y: int) -> None:
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        memory.note_file("event.log", f"pop_up visible={self.isVisible()} geom={self.geometry()}", self.cfg)

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(ev)

    # ---------- 一问一答 ----------
    def _submit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self.hide()
        self.submit_text(text, "typed")

    def submit_text(self, text: str, source: str = "typed") -> None:
        """外面也能往这儿递一句：语音听来的走这条路，跟打字汇到同一个脑子。

        source 只能是人的两种（`typed` / `voice`，见 `turn.HUMAN`）；
        别的来源别走输入框——输入框是人说话的地方。
        """
        text = (text or "").strip()
        if not text:
            return
        import turn
        if source not in turn.HUMAN:
            raise ValueError(f"输入框只收人说的话，不收 {source!r}")
        tag = "月下(说)" if source == "voice" else "月下"
        memory.note_file("chat.log", f"{tag}: {text}", self.cfg)
        try:
            memory.log_say(self.cfg, "月下", text)          # 4-4：共享月志
        except Exception:                        # noqa: BLE001
            pass
        if getattr(self, "_said", None):
            try:
                self._said(text)                     # 舞台气泡：人说的话也往上叠
            except Exception:                        # noqa: BLE001
                pass
        self.history.append({"role": "user", "content": text})
        try:
            import session
            session.append(self.cfg, "main", "user", text, source=source, entry="chat")
        except Exception as e:                   # noqa: BLE001
            # 3-3：记不上也照常说下一句；聊天是主，落盘是副。
            memory.note_file("tool.log", f"会话没存上：{type(e).__name__} {e}", self.cfg)
        # 4-2：如果这句是「确认 d-xxxx」，在叫模型之前就把草稿发掉；模型碰不到。
        try:
            import outbox as _outbox
            _done = _outbox.confirm_if_any(text, source)
        except Exception:                        # noqa: BLE001
            _done = None
        if _done:
            self.history.append({"role": "assistant", "content": _done})
            try:
                import session
                session.append(self.cfg, "main", "assistant", _done, entry="chat")
            except Exception:                    # noqa: BLE001
                pass
            self._say(_done, 5.0)
            return
        self._say(__import__("i18n").t("bubble.thinking"), 2.0)
        threading.Thread(target=self._ask, args=(text, source), daemon=True).start()

    def _ask(self, text: str, source: str) -> None:
        import tools as toolmod

        def on_start(name: str, args: dict) -> None:
            try:
                self._bridge.status.emit(toolmod.status_line(name, args))
            except Exception:
                pass

        def on_tool(name: str, args: dict, result: str) -> None:
            try:
                brief = _json.dumps(args, ensure_ascii=False)[:120]
            except Exception:
                brief = str(args)[:120]
            memory.note_file("tool.log", f"{name} {brief} -> {str(result)[:90]}", self.cfg)

        answer = llm.talk(text, self.history[:-1], self.cfg, source=source, entry="chat",
                          on_tool=on_tool, on_start=on_start)
        self._bridge.got.emit(answer)

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
            session.append(self.cfg, "main", "assistant", answer, entry="chat")
        except Exception as e:                   # noqa: BLE001
            memory.note_file("tool.log", f"会话没存上：{type(e).__name__} {e}", self.cfg)
        # 3-3 改：以前是 del self.history[:-12]，12 条一满就把旧话丢掉；
        # 现在盘上留 200 条、内存留 40 条，喂给模型仍然只取最后 12 条（llm 那边管）。
        del self.history[:-40]
        try:
            memory.log_say(self.cfg, "我", answer)          # 4-4：她的回答也进月志
        except Exception:                        # noqa: BLE001
            pass
        # 气泡停久一点：2 秒就散，人一抬头就没了（01:11 月下就吃过这个亏）
        self._say(answer, max(6.0, min(24.0, len(answer) / 6.0)))
