"""模板插件 —— 改这个名字、改这几个工具，就是你的插件了。

规矩看 `devkit/README.md`；自测：`py -3 devkit\\check.py plugins\\我的插件.py`。
"""
from __future__ import annotations

# ---- 给人看的三样（设置页、市场列表都用它们）----
NAME = "模板"
ABOUT = "一句话说明这个插件干什么。"
ICON = "模"

# ---- 设置项：设置页照着这张表自己长界面 ----
# kind 只能是 text / int / bool / lines
SETTINGS = [
    {"key": "greeting", "label": "打招呼的话", "kind": "text",
     "hint": "冒泡时说的第一句"},
    {"key": "limit", "label": "每天最多几次", "kind": "int", "hint": "默认 3"},
    {"key": "enabled", "label": "开着", "kind": "bool", "hint": ""},
]

# 设置存在 config.json 的哪一格；不写就跟插件名同名
SETTINGS_SECTION = "template"

_COUNT = 0


# ---- ctx 只给一次，自己留着 ----
_CTX: dict = {}


def setup(ctx: dict) -> None:
    """装的时候跑一次。要主动说话，只在这里挂 hooks。"""
    global _CTX
    _CTX = ctx
    # ctx["hooks"].push("……")  # 塞进下一轮
    # ctx["hooks"].wake("……")  # 立刻起一轮（这一轮不许动电脑）
    # ctx["hooks"].say("……")   # 直接冒泡


def status():
    """设置页那盏灯：(亮不亮, 一句话)。不写也行。"""
    return True, f"今天说了 {_COUNT} 次"


# ---- 工具：函数收一个 args 字典，返回字符串；不许抛异常 ----
def _hello(args: dict) -> str:
    global _COUNT
    cfg = (_CTX.get("config") or {}).get(SETTINGS_SECTION) or {}
    word = str(cfg.get("greeting") or "在呢")
    who = str((args or {}).get("who") or "你")
    _COUNT += 1
    return f"{word}，{who}。"


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "template_hello",
                "description": "打个招呼，回一句。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "who": {"type": "string", "description": "跟谁打招呼，可不填"},
                    },
                },
            },
        },
        _hello,
    ),
]
