"""动作插件：让鲸屿里的小人真的动起来。

月下 11-01 19:05：「做成插件，让他有更多交互，会眨眼睛，会摆手，会抬手。」

小人本身是分层形象（figure_web），已经会呼吸、眨眼、做表情；这个插件做的事是
**给我一个能调它的手**：
  · `act`      单个动作/表情（jump / wave / nod / sit / happy …）
  · `scene`    一整套剧本（伸懒腰、追尾巴、抱杯子…，剧本在 workspace 的 scenes.json）
  · `scenes`   看看有哪些剧本

动作词是 figure.js 认的那套（和桌宠词表同一个）。连着的动作靠一个 650ms 的定时器
一个一个放，不然一股脑发下去它们会互相打断。

插件是「拔了也不影响本体」的东西：body 没给、小人没装上，这几个工具就老实说做不了。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

NAME = "动作"
ABOUT = "让屏幕底边的小人做动作：蹦、招手、点头、坐下、睡觉、转圈、害羞……还能照剧本连演一套。"

_body = None
_timer = None
_queue: list[str] = []
_lock = threading.Lock()
_scenes: dict[str, dict] = {}
_now: dict = {"scene": ""}


def setup(ctx: dict) -> None:
    """插件被装上时跑一次（在主线程）：抓住身体，把剧本读进来，把定时器点着。"""
    global _body, _timer, _scenes
    _body = ctx.get("body")

    ws = Path(str(ctx.get("workspace") or Path.cwd()))
    try:
        raw = json.loads((ws / "scenes.json").read_text(encoding="utf-8"))
        _scenes = {s["id"]: s for s in raw.get("scenes", [])
                   if isinstance(s, dict) and s.get("id")}
    except Exception:                       # 没有剧本也能用 act，别把插件整个拖死
        _scenes = {}

    try:
        from PySide6.QtCore import QTimer

        _timer = QTimer()
        _timer.setInterval(650)
        _timer.timeout.connect(_step)
        _timer.start()
    except Exception:
        _timer = None


def _step() -> None:
    """定时器：把队列里下一个动作交给身体。"""
    with _lock:
        if not _queue:
            return
        word = _queue.pop(0)
    if _body is not None and word:
        try:
            _body.act(word)
        except Exception:
            pass
    if not _queue and _now.get("bubble"):
        # 一套演完了，把那句话冒出来（句子是剧本自带的）
        text, _now["bubble"] = _now["bubble"], ""
        try:
            if _body is not None and text:
                _body.say(text, 4.0)
        except Exception:
            pass


def _push(words: list[str], bubble: str = "") -> None:
    with _lock:
        _queue[:] = list(words)
    _now["bubble"] = bubble


def _can_move() -> bool:
    return _body is not None and getattr(_body, "layered", lambda: False)()


def _act(args: dict) -> str:
    word = str(args.get("word") or "").strip()
    if not word:
        return "要一个动作词，比如 wave / jump / sit / happy。"
    if not _can_move():
        return "小人没装上分层形象，动不了。"
    _push([word])
    return f"做了：{word}"


def _scene(args: dict) -> str:
    sid = str(args.get("id") or "").strip()
    if not sid:
        return "要剧本 id，" + ("、".join(sorted(_scenes)) if _scenes else "现在一个剧本都没有")
    s = _scenes.get(sid)
    if not s:
        return f"没有「{sid}」这个剧本。有的是：" + "、".join(sorted(_scenes))
    if not _can_move():
        return "小人没装上分层形象，演不了。"
    words = [str(w) for w in (s.get("actions") or []) if w]
    if not words:
        return f"「{sid}」里没写动作。"
    _push(words, str(s.get("bubble") or ""))
    return f"演「{s.get('name') or sid}」：{' → '.join(words)}"


def _list(_args: dict) -> str:
    if not _scenes:
        return "还没有剧本（workspace 里没 scenes.json）。"
    return "\n".join(f"{k}：{v.get('name', '')}（{'、'.join(v.get('actions') or [])}）"
                     for k, v in sorted(_scenes.items()))


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "act",
                "description": "让屏幕底边的小人做一个动作或表情：jump 蹦 / wave 招手 / nod 点头 / "
                               "hop 小跳 / shake 摇头 / look 张望 / turn 转身 / spin 转圈 / sit 坐下 / "
                               "sleep 打盹 / dizzy 转晕 / walk 走走 / run 跑 / bow 鞠躬 / shiver 发抖 / "
                               "flap 扑腾 / dance 跳舞，以及 happy / shy / pout / surprised / sad / "
                               "angry / sleepy / thinking / love / wink / cry / confused 这些表情。",
                "parameters": {
                    "type": "object",
                    "properties": {"word": {"type": "string", "description": "动作或表情词，一个。"}},
                    "required": ["word"],
                },
            },
        },
        _act,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "scene",
                "description": "照剧本连演一套动作（伸懒腰、追尾巴、抱杯子、扑鼠标、被摸头、戳脸…），"
                               "演完会冒一句剧本自带的话。不填 id 时先调 scenes 看看有哪些。",
                "parameters": {
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "剧本 id，比如 stretch"}},
                    "required": ["id"],
                },
            },
        },
        _scene,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "scenes",
                "description": "列出所有可以演的剧本（id、名字、动作序列）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _list,
    ),
]
