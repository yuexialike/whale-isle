"""插件跟这个家说话的三个口子。

2026-11-01 21:52 月下说要把 Coop 上那套 QQ 插件搬进鲸屿。看过它的源码就明白：
插件光能「被叫」不够（那是现在 `plug.py` 只给 `TOOLS` 的样子），它还得能

  · `push(text)`   往下一轮塞一段话 —— QQ 来消息了，得让我这一轮看见；
  · `wake(reason)` 立刻叫醒脑子起一轮 —— 不然只能等心跳，最久半小时；
  · `say(text)`    直接冒个气泡 —— 不需要思考的那种提示（「QQ 断线了」）。

谁把这些接上：`main.py` 开机时 `HOOKS.bind(wake=…, say=…)`。
接上之前：`push` 的话先攒着（最多 `MAX_PENDING` 条，旧的挤掉），`wake` 只记一笔日志，不炸。
——插件是别人写的，插件写坏了不能把这个家带塌（`plug.py` 本来就是这个脾气）。

`llm.py` 每轮拼消息时会 `take()` 走攒着的话，**取走就清空**（像信箱，不是广播）。
"""
from __future__ import annotations

import datetime
import threading

MAX_PENDING = 20          # 攒太多说明脑子根本没转，留着也没意义
MAX_CHARS = 1200          # 一条塞太长会把这一轮挤爆


class Hooks:
    def __init__(self) -> None:
        self._wake = None
        self._say = None
        self._pending: list[str] = []
        self._lock = threading.Lock()
        self._log = None          # set_log(fn)：main 那边给一条写日志的路

    # ------------------------------------------------------------ 接线
    def bind(self, wake=None, say=None, log=None) -> None:
        """main.py 开机时调。给什么接什么，没给的那样保持「攒着/记日志」。"""
        if wake is not None:
            self._wake = wake
        if say is not None:
            self._say = say
        if log is not None:
            self._log = log

    def _note(self, text: str) -> None:
        try:
            if self._log is not None:
                self._log(text)
            else:
                print(f"[hooks] {text}")
        except Exception:                            # noqa: BLE001
            pass

    # ------------------------------------------------------------ 塞话
    def push(self, text: str, source: str = "插件") -> bool:
        """往下一轮塞一句。回 False 表示空话或塞不进去（不抛异常）。"""
        text = (text or "").strip()
        if not text:
            return False
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "…（截断了）"
        stamp = datetime.datetime.now().strftime("%H:%M")
        line = f"[{stamp}] {source}：{text}"
        with self._lock:
            self._pending.append(line)
            del self._pending[:-MAX_PENDING]
        return True

    def take(self) -> str:
        """把攒着的话一次取走（取完就空）。没有就回空串。

        3-4 起：碰触攒的账（`touch_notes`）排在最前面，作为这一轮开头的一句附注。
        它自己不叫醒模型——只有真开口/真被叫醒的这一轮，这些账才跟着被取走。
        """
        touch = ""
        try:
            import touch_notes
            touch = touch_notes.take()
        except Exception:                            # noqa: BLE001
            touch = ""
        with self._lock:
            said = "\n".join(self._pending)
            self._pending.clear()
        return "\n".join(x for x in (touch, said) if x)

    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    # ------------------------------------------------------------ 叫醒
    def wake(self, reason: str = "") -> bool:
        """立刻起一轮。回 False 表示没人接线（这会儿只能记一笔）。"""
        reason = (reason or "").strip()
        if self._wake is None:
            self._note(f"想醒一下（{reason or '没写由头'}），但还没接线")
            return False
        try:
            self._wake(reason)
            return True
        except Exception as e:                       # noqa: BLE001
            self._note(f"叫醒失败：{type(e).__name__} {e}")
            return False

    # ------------------------------------------------------------ 冒泡
    def say(self, text: str, seconds: float = 6.0) -> bool:
        """不经过脑子，直接冒个气泡。回 False 表示没接线。"""
        text = (text or "").strip()
        if not text or self._say is None:
            return False
        try:
            self._say(text, seconds)
            return True
        except Exception as e:                       # noqa: BLE001
            self._note(f"冒泡失败：{type(e).__name__} {e}")
            return False


HOOKS = Hooks()      # 全家共一个。插件拿 `ctx["hooks"]`，脑子那边 `import hooks`
