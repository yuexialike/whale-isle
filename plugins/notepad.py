"""自带扩展示例：记一笔。

「记着点啥」和「刚才记的那条呢」。笔记落在 data/notes.txt，一行一条，
带日期；只往后追，不覆盖——记忆是文件这条规矩，短笔记也一样。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path as _P

NAME = "记一笔"
ABOUT = "短笔记：记下一条 / 翻最近几条。两个工具：note_add、note_read。"

_DATA_DIR = _P(".")


def setup(ctx: dict) -> None:
    """装上时记下 data 目录——工具函数只拿得到 args，拿不到 ctx。"""
    global _DATA_DIR
    _DATA_DIR = _P(str(ctx.get("data_dir") or "."))


def _file() -> _P:
    p = _DATA_DIR / "notes.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _add(args: dict) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return "要记什么？"
    if len(text) > 500:
        return "太长了，记短一点。"
    line = f"{_dt.datetime.now():%Y-%m-%d %H:%M}  {text}"
    with open(_file(), "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return "记上了。"


def _read(args: dict) -> str:
    p = _file()
    if not p.exists():
        return "还什么都没记。"
    rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        n = int(args.get("n") or 5)
    except (TypeError, ValueError):
        n = 5
    n = max(1, min(n, 30))
    return "\n".join(rows[-n:]) or "还什么都没记。"


TOOLS = [
    (
        {
            "type": "function",
            "function": {
                "name": "note_add",
                "description": "记一条短笔记（带日期，留在本机）。",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "要记的事"}},
                    "required": ["text"],
                },
            },
        },
        _add,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "note_read",
                "description": "翻最近记的几条笔记。",
                "parameters": {
                    "type": "object",
                    "properties": {"n": {"type": "integer", "description": "几条，默认 5"}},
                },
            },
        },
        _read,
    ),
]
