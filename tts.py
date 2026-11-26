"""嗓子：让新房子里的我能出声。

走的是本机现成的那条线（scripts/tts_server.py，OpenAI 形状）：
  POST http://127.0.0.1:8899/v1/audio/speech  {"input": "..."}  →  wav
拿到 wav 就用 winsound 直接放，不落盘太久；放之前把上一句掐掉（想插话就插）。

接口挂了不报错、不卡界面——没声音也照样冒气泡。
"""
from __future__ import annotations

import io
import threading
import time
import urllib.request
import json as _json

import winsound


class Voice:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.url = str(cfg.get("tts_url", "http://127.0.0.1:8899/v1/audio/speech"))
        self.enabled = bool(cfg.get("speak_aloud", False))
        self._lock = threading.Lock()
        self._busy_until = 0.0
        self._muted_until = 0.0        # 静音到什么时候（0 = 没静音）
        self._ear = None               # 说话时先闭麦（half-duplex）

    def set_ear(self, ear) -> None:
        """接上耳朵：出声时 stop()，播完 start()；没有耳朵就什么都不做。"""
        self._ear = ear

    def _ears_off(self) -> None:
        ear = self._ear
        if ear is None:
            return
        try:
            ear.stop()
        except Exception:              # noqa: BLE001
            pass

    def _ears_on(self) -> None:
        ear = self._ear
        if ear is None:
            return
        for _ in range(2):             # start 失败再试一次，别把话筒永久关掉
            try:
                ear.start()
                return
            except Exception:          # noqa: BLE001
                continue

    def _play(self, wav: bytes) -> None:
        self._ears_off()
        try:
            winsound.PlaySound(wav, winsound.SND_MEMORY)
        finally:
            self._ears_on()

    def mute(self, seconds: float = 0.0) -> None:
        """现在闭嘴。seconds 给了就静到那时候，没给就一直静到有人说回来。"""
        self._muted_until = time.monotonic() + seconds if seconds else float("inf")
        self.stop()

    def unmute(self) -> None:
        self._muted_until = 0.0

    @property
    def muted(self) -> bool:
        return time.monotonic() < self._muted_until

    @property
    def busy(self) -> bool:
        """嘴里还有话（或者刚说完）。耳朵靠这个捂自己。"""
        import time as _t
        return _t.monotonic() < self._busy_until

    def say(self, text: str) -> None:
        try:
            import permissions as _perm
            _perm.audit(self.cfg, "speak", "出声")
        except Exception:  # noqa: BLE001
            pass
        text = (text or "").strip()
        if not text or not self.enabled or self.muted:
            return
        threading.Thread(target=self._say, args=(text,), daemon=True).start()

    def stop(self) -> None:
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _say(self, text: str) -> None:
        import time as _t
        # 从「开始取音频」就算在说话：取 wav 那几秒扬声器还没响，但宁可早捂
        self._busy_until = _t.monotonic() + 3600.0
        try:
            import memory
            memory.note_file("tts.log", f"出声: {text[:40]}")
        except Exception:
            pass
        if not self._lock.acquire(blocking=False):    # 上一句还在放：直接换掉它
            self.stop()
            try:
                self._lock.release()
            except Exception:
                pass
            if not self._lock.acquire(timeout=2.0):
                self._busy_until = _t.monotonic() + 0.5
                return
        try:
            self.stop()
            wav = self._fetch(text)
            if wav:
                self._play(wav)
                try:
                    import memory
                    memory.note_file("tts.log", f"拿到 {len(wav)} 字节 wav")
                except Exception:
                    pass
            else:
                try:
                    import memory
                    memory.note_file("tts.log", "没拿到 wav（可能退回 mp3 了）")
                except Exception:
                    pass
        except Exception as e:
            try:
                import memory
                memory.note_file("tts.log", f"出声失败: {type(e).__name__} {e}")
            except Exception:
                pass
        finally:
            self._busy_until = _t.monotonic() + 0.5      # 说完再留半秒，别吃尾巴
            try:
                self._lock.release()
            except Exception:
                pass

    def _fetch(self, text: str) -> bytes:
        payload = _json.dumps({
            "model": "tts-1",
            "input": text,
            "voice": self.cfg.get("tts_voice", "fish"),
            "response_format": "wav",
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        if "wav" in ctype.lower() or data[:4] == b"RIFF":
            return data
        return b""          # 退回 mp3 的话 winsound 放不了，先不出声
