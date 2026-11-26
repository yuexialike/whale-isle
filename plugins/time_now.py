"""示例插件：现在几点。

心跳醒来的时候脑子常常不知道今天是哪天、几点——问一句这个就行。
写它主要是给「插件长什么样」立个样子：一个文件、一个 TOOLS、没有别的。
"""
from __future__ import annotations

import datetime as _dt

NAME = "现在几点"
ABOUT = "让它知道今天是哪天、现在几点。一个工具：now。"

_WEEK = "一二三四五六日"


def _now(_args: dict) -> str:
    t = _dt.datetime.now()
    return f"现在 {t:%Y-%m-%d %H:%M}（星期{_WEEK[t.weekday()]}）"


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "now",
                "description": "现在几点、今天几号星期几（本机时间）。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _now,
    ),
]
