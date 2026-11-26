"""把新家这 20 个工具，整理成 Coop 那边 World 看得懂的一张清单，并替它转接调用。

谁用它：`bridge/pet_sidecar.py`（一个只靠一行行文字跟外面说话的小程序）会
`import world_tools`——外面问「你有哪些工具」就调 `describe()`，要「用某个工具」
就调 `call()`；`test_world_tools.py` 也直接调这两个。

这个文件只做三件事：
  describe()        20 条工具 → 一张清单（名字、说明、参数、一个标签）
  call(name, args)  开一轮（说话的人是「插件」）→ 交给 tools.run → 回 {text, failed}
  tags_for(name)    按名字给出「只读 / 动手 / 看一眼屏幕」的标签

不 import Qt、不碰网络、不改 tools.py。

哪几行是照 Coop 的做法、哪几行是我们自己写的：
  · 清单的字段（name / description / parameters / tags，tags 只有 read / act / snapshot
    三种）是照着 Cortico 源码里 ToolDef 的样子写的（build/cortico/src/core/types.ts）——
    只是照着样子写，不是抄它的代码；
  · describe / tags_for / call / _looks_failed 和下面这几张归类表，都是我们自己写的。
"""
from __future__ import annotations

# Cortico 的 ToolTag 只有这三个值（types.ts 里 ToolSchema 的 tags）。
ALLOWED_TAGS = ("read", "act", "snapshot")

# 只读的三件 + 看屏幕那两件（看屏幕也算 read，另加 snapshot）。
_READ_ONLY = {
    "list_memory", "read_memory", "list_alarms", "list_windows",
}
_SNAPSHOT = {"see_screen", "zoom"}

# 剩下这些是动东西的（写记忆、闹钟、键鼠、终端）。
_ACT = {
    "write_memory", "note", "set_alarm", "cancel_alarm",
    "click", "move_mouse", "scroll", "type_text", "press_keys",
    "hold_keys", "hold_mouse", "focus_window", "drag", "run_command",
}


def tags_for(name: str) -> list[str]:
    """一个工具该挂哪些标签。认不出来的一律按 read 处理，但**不留空**。"""
    tags: list[str] = []
    if name in _READ_ONLY or name in _SNAPSHOT:
        tags.append("read")
    if name in _ACT:
        tags.append("act")
    if name in _SNAPSHOT:
        tags.append("snapshot")
    return tags or ["read"]


def describe() -> list[dict]:
    """20 条工具的中性描述（JSON 可序列化，侧车能直接发）。

    只取 `tools.TOOLS`（核心 20 条）；插件挂进来的 `EXTRA` 不在这层——
    那是 3-2 的事，等插件有 manifest 再说。
    """
    import tools

    out: list[dict] = []
    for schema in tools.TOOLS:
        fn = schema.get("function") or {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "description": str(fn.get("description") or "").strip(),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            "tags": tags_for(name),
        })
    return out


def count() -> int:
    return len(describe())


def call(name: str, args: dict | None = None) -> dict:
    """按名字跑一个工具。

    这里开的是 `source="plugin"` 的轮——桥接进来的调用没有「人类来源」，
    所以看屏幕/动键鼠/终端会被闸门拒。**拒也是一条正常回执**，不是错误。
    """
    import tools
    import turn

    payload = dict(args or {})
    with turn.open("plugin", "bridge"):
        text = tools.run(name, payload)
    return {"text": text, "failed": _looks_failed(text)}


def _looks_failed(text: str) -> bool:
    """从回执里认“这次没成”。只认这几种前缀，别把 `（退出码 0）` 当失败。"""
    head = (text or "")[:12]
    return any(mark in head for mark in (
        "（工具 ", "（不让", "（没有这个工具", "（闸门没装上",
    ))
