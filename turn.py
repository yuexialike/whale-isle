"""轮：这一轮是谁在说话。

为什么要单独一层：
  以前「来源」是 `tools` 里的一个全局变量（`tools.turn()`），谁都能改；而且是在 UI
  线程里设、在另一个线程里用。谁后设谁算数，漏设的那一轮就继承上一轮——
  上一次是人打字，闹钟到点那一轮也带着 `typed`。
  现在改成：开轮的时候定死，只读，跟着线程走（`contextvars`），退出自动收。

谁能开轮：只有 `llm.talk()`（一轮模型调用）和测试。别的地方要用，就调 `llm.talk`。
`turn.open` 不给人「先设一下、过会儿再用」的机会——那是老毛病。

规则：
  只有 `HUMAN` 里的两种算「人说的」：`typed`（对话页/输入框打的字）、`voice`（按住 F9 说的话）。
  网页、插件、心跳、闹钟、系统自己、自检，一律不算——闸门见到就拒。
  不在 `ALL` 里的字符串直接 `ValueError`：拼错了要当场炸，不许当没事。

日志：`data/turn.log`，一轮两行（`+` 开、`-` 完）。「完」那行带 `refused=`，
  以后查「哪一轮被闸门拒了」只认这一列。
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as _dt
import itertools
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# 人说的：只有这两种能当「用电脑」的理由。
HUMAN = ("typed", "voice")

# 未必是人说的，得看是谁：`qq` 只在发送者号落在白名单里时才算。
# 它**不进 HUMAN**——HUMAN 的意思是「这句一定是人说的」，qq 还得再验一次号码，
# 那一道在 gate.py 的 _why 里。（11-24 14:41 他说的「改吧」。）
QQ = ("qq",)

# 不是人说的：各自有各自的入口，全都只许看记忆、不许动电脑。
OTHER = ("heartbeat", "plugin", "web", "alarm", "system", "selftest")

ALL = HUMAN + QQ + OTHER

# turn.open 的 meta 白名单：note 是诊断用，sender 只给 qq 用（见 open()）。
# `input` 故意不在里面——那一格只能由 input_provenance 写，调用方传 input 会当场 TypeError。
_ALLOWED_META = ("note", "sender")

# 拒绝的时候怎么称呼它（给闸门说人话用）。
LABEL = {
    "typed": "你打的字",
    "voice": "你说的话",
    "qq": "QQ 上说的话",
    "heartbeat": "心跳",
    "plugin": "插件",
    "web": "网页",
    "alarm": "闹钟",
    "system": "系统",
    "selftest": "自检",
}


@dataclass(frozen=True)
class Turn:
    """一轮。开出来就只读；`counter` 是给闸门记「这轮拒了几次」用的。"""

    id: str
    source: str
    entry: str = ""
    started: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)
    counter: dict = field(default_factory=dict, compare=False, repr=False)

    def is_human(self) -> bool:
        return self.source in HUMAN


_CURRENT: contextvars.ContextVar[Turn | None] = contextvars.ContextVar("pet_turn", default=None)

_SEQ = itertools.count(1)
_WRITE_LOCK = threading.Lock()
_PATH: Path | None = None


# ---------------------------------------------------------------- 对外

def now() -> Turn | None:
    """这一轮；不在轮里就是 None。"""
    return _CURRENT.get()


def human() -> bool:
    """这一轮算不算「人说的」。"""
    t = _CURRENT.get()
    return bool(t and t.source in HUMAN)


def label(source: str | None) -> str:
    """来源的名字；拼错的原样回，别替它圆。"""
    if not source:
        return "没有来源"
    return LABEL.get(source, source)


def refused(t: Turn | None = None) -> int:
    """这一轮被闸门拒了几次。"""
    t = t if t is not None else _CURRENT.get()
    return int(t.counter.get("refused", 0)) if t is not None else 0


def count_refusal() -> None:
    """闸门拒一次就记一笔（它自己调；别人别调）。"""
    t = _CURRENT.get()
    if t is not None:
        t.counter["refused"] = int(t.counter.get("refused", 0)) + 1


@contextlib.contextmanager
def open(source: str, entry: str = "", **meta):
    """开一轮。用法：`with turn.open("typed", "page"): ...`

    未知来源 → ValueError（拼错了当场炸）。
    同一线程里上一轮还没退 → RuntimeError（不静默覆盖，也不嵌娃）。
    meta 只认白名单（note、以及只给 qq 用的 sender）；`input` 不在白名单里，传了直接 TypeError——
    那一格只能由 `input_provenance` 写，不许调用方自己报家门。
    qq 来源必须带 sender（纯数字 QQ 号），不带或不是数字当场 ValueError。
    """
    if source not in ALL:
        raise ValueError(f"不认识的来源：{source!r}（只认 {', '.join(ALL)}）")
    bad = [k for k in meta if k not in _ALLOWED_META]
    if bad:
        raise TypeError(f"turn.open 不接这些 meta 键：{', '.join(bad)}；"
                        f"input 只能由 input_provenance 写")
    if "sender" in meta and source != "qq":
        raise TypeError("sender 只给 qq 来源用；别的来源别自己报家门")
    meta = dict(meta)
    if source == "qq":
        # 谁在 QQ 上说的？只认号码，不认昵称、不认群名、不认自称。
        sender = str(meta.get("sender") or "").strip()
        if not sender.isdigit():
            raise ValueError("qq 来源必须带 sender（纯数字 QQ 号）")
        meta["sender"] = sender
    before = _CURRENT.get()
    if before is not None:
        raise RuntimeError(f"上一轮还没完（{before.id} {before.source}），不能再开一轮")

    if source == "typed":
        # 这一轮的字是物理键盘敲的，还是程序 SendInput 塞进来的？
        # 钩子没起来时必须是 provenance_unavailable，不能和「最近没输入」的 unknown 混在一起。
        try:
            import input_provenance as _prov
            meta["input"] = _prov.classify() if _prov.available() else "provenance_unavailable"
        except Exception:                       # noqa: BLE001
            meta["input"] = "provenance_unavailable"

    t = Turn(id=f"{next(_SEQ) & 0xFFFF:04x}", source=source, entry=str(entry or ""),
             started=time.time(), meta=meta)
    _note(f"+ {t.id}  source={t.source:<9}  entry={(t.entry or '-'):<9}  "
          f"thread={threading.current_thread().name}{_meta_text(t.meta)}")
    token = _CURRENT.set(t)
    try:
        yield t
    finally:
        _CURRENT.reset(token)
        dur = int((time.time() - t.started) * 1000)
        _note(f"- {t.id}  source={t.source:<9}  dur={dur}ms  refused={refused(t)}")


# ---------------------------------------------------------------- 内部

def _meta_text(meta: dict) -> str:
    if not meta:
        return ""
    body = " ".join(f"{k}={v}" for k, v in meta.items())
    return f"  meta={body}"


def _path() -> Path:
    """`data/turn.log` 的路径。第一次问的时候定下来，别每轮都去读 config + 验封印。"""
    global _PATH
    if _PATH is None:
        try:
            import memory
            base = Path(memory.data_dir())
        except Exception:                       # noqa: BLE001
            base = Path(__file__).resolve().parent / "data"
        _PATH = base / "turn.log"
    return _PATH


def _note(line: str) -> None:
    """记一行。写不进去就算了——日志不能把一轮搞死。"""
    try:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _WRITE_LOCK:
            # 这里不能写 `open(...)`：本模块的 `open()` 是上面那个开轮的，会把内建 open 遮住。
            with _path().open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {line}\n")
    except Exception:                           # noqa: BLE001
        pass
