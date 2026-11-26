"""耳朵接进身体：听到人话就交出去。

两种模式（`config.json` 的 `ear_mode`）：

  "hold"    **按住说话**。按住 `ear_key`（默认 F9）才录，松开就认字。
            麦克风虽然一直开着，但没按的时候一个字节都不留。
  "always"  常开。听到声音就记，静 0.9 秒收句。
            晚上试过——它会听见自己说话，然后回自己，来回打转。先别当默认。

`off`（或者 `ears: false`）就不装耳朵。

一条线程在那儿等（工作线程里不能画界面，认完的字经 Qt signal 送回主线程）。
`deaf_for()` / `pause_check` 是捂耳朵的：我一出声，麦克风就会把我的声音听回来，
所以说话这段时间不录——不然会自己跟自己聊一晚上。
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal


class Ears(QObject):
    heard = Signal(str)
    holding = Signal(bool)          # 按下 / 松开：界面上的「🎤 在听……」小框靠它
    note = Signal(str)              # 一句短提示（没听清 / 我在说话丢了）

    def __init__(self, cfg: dict | None = None, min_chars: int = 2) -> None:
        super().__init__()
        cfg = cfg or {}
        self.mode = str(cfg.get("ear_mode", "hold")).strip().lower() or "hold"
        self.key_name = cfg.get("ear_key", "f9")
        self.mic_device = cfg.get("mic_device", "")      # 空 = 系统默认；也可以是设备号或名字里的一段
        try:                                             # 让 ears 里那几条开麦的路都认这个选择
            import ears as _ears
            _ears.DEFAULT_DEVICE = self.mic_device
        except Exception:                                # noqa: BLE001
            pass
        self.min_chars = min_chars
        self.pause_check = None          # 回调：True 表示「我正出声，别听」
        self._stop = threading.Event()
        self._deaf_until = 0.0
        self._last_text = ""
        self._last_at = 0.0
        self._thread: threading.Thread | None = None

    # ---------- 开关 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ears", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def deaf_for(self, seconds: float) -> None:
        """自己说话的时候先聋一会儿。"""
        until = time.monotonic() + max(0.0, seconds)
        if until > self._deaf_until:
            self._deaf_until = until

    @property
    def deaf(self) -> bool:
        if time.monotonic() < self._deaf_until:
            return True
        if self.pause_check is not None:
            try:
                return bool(self.pause_check())
            except Exception:
                return False
        return False

    # ---------- 干活 ----------
    def _note(self, line: str) -> None:
        try:
            import memory
            memory.note_file("ears.log", line)
        except Exception:
            pass

    def _loop(self) -> None:
        import ears

        if not ears.available():
            self._note(f"模型不在，耳朵不开: {ears.MODEL_DIR}")
            return

        if self.mode == "always":
            self._note("耳朵开了（常开）")
            self._loop_always(ears)
        else:
            vk = ears.resolve_vk(self.key_name)
            self._note(f"耳朵开了（按住 {self.key_name} / vk={vk} 说话）")
            self._loop_hold(ears, vk)

    def _take(self, ears, text: str, secs: float, forced: bool = False) -> None:
        """一句认完了：过滤、去重，然后交给主线程。

        `forced=True` 是按住 F9 那种：**手是他自己按下去的**，那就是他要说话，
        不再拿「我正出声」去挡（11-04 19:07 他正是边说边被我丢了，以为耳朵坏了）。
        """
        text = (text or "").strip()
        if not text:
            return
        if not ears.looks_like_speech(text):
            self._note(f"当噪声丢了: {text[:30]}")
            return
        if len(text) < self.min_chars:
            self._note(f"太短，丢了: {text}")
            self.note.emit(f"只听到「{text}」")
            return
        if self.deaf and not forced:        # 录的过程中我自己开口了，这句不算
            self._note(f"我正出声，丢了: {text[:30]}")
            self.note.emit("我刚才在说话，这句没送出去")
            return

        now = time.monotonic()
        if text == self._last_text and now - self._last_at < 4.0:
            return                          # 同一句被录了两遍
        self._last_text, self._last_at = text, now

        self._note(f"听到 {secs:.1f}s: {text}")
        self.heard.emit(text)

    def _loop_hold(self, ears, vk: int) -> None:
        mic = None
        try:
            mic = ears.open_mic()
            self._note("麦克风开了一次，之后一直用它")
        except Exception as e:                       # noqa: BLE001
            self._note(f"麦克风打不开，改成每次按了再开: {type(e).__name__} {e}")
        while not self._stop.is_set():
            try:
                text, secs = ears.listen_hold(
                    vk, mic=mic,
                    on_press=lambda down: self.holding.emit(bool(down)))
            except Exception as e:                   # noqa: BLE001
                self._note(f"录音出错: {type(e).__name__} {e}")
                if mic is not None:
                    try:
                        mic.close()
                    except Exception:                # noqa: BLE001
                        pass
                    mic = None
                time.sleep(2.0)
                if not self._stop.is_set():
                    try:
                        mic = ears.open_mic()
                        self._note("麦克风重开了一次")
                    except Exception as e2:          # noqa: BLE001
                        self._note(f"重开麦克风失败: {type(e2).__name__} {e2}")
                continue
            self.holding.emit(False)
            self._take(ears, text, secs, forced=True)

    def _loop_always(self, ears) -> None:
        while not self._stop.is_set():
            if self.deaf:
                time.sleep(0.2)
                continue
            try:
                text, secs = ears.listen_once(quiet_sec=0.9, max_sec=20.0, start_timeout=2.0)
            except Exception as e:
                self._note(f"录音出错: {type(e).__name__} {e}")
                time.sleep(2.0)
                continue
            self._take(ears, text, secs)
