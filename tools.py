"""工具层：我能做的事，一块一块。

规矩（比 Coop 严的一条）：
  - 所有路径必须在工作区里面，跑出去一律拒。不靠提示词，靠 `_inside()`。
  - 写和读自己的记忆**不问人**——那是我的纸笔。
  - 删东西暂时不提供。删是不可逆的，等有了「问」的界面再说。
  - 要动电脑（截图、键鼠）的工具，全部走 `gate.Gate` 的门口，
    不在这儿自己判断谁能叫我动。

一个工具 = 声明（给模型看的）+ 实现（真做的事）+ 一句「吐什么」。
"""
from __future__ import annotations

from pathlib import Path

import memory
from gate import Refused

# 闸门装在这儿，不装在每个工具里。工具层只管「要动手了，去门口问一声」。
_gate = None
LAST_IMAGE: str | None = None     # 刚截的那张图，交给 llm 贴进 messages


def bind(gate) -> None:
    """开机时把门装上。之后所有要动电脑的工具都从它门口过。"""
    global _gate
    _gate = gate


def source() -> str:
    """这一轮是谁说的（只读，来自 turn）。没有轮就回 "-"。"""
    import turn
    t = turn.now()
    return t.source if t is not None else "-"


# ---------------------------------------------------------------- 插件
# 插件就是「额外能做的事」，不写进这个文件。做法和工具一样：
#   `plug.py` 里 `register(schema, fn)` 挂进来，`run()` 最后照名字找。
# 为什么不在 `run()` 里加一堆 if：插件是**从月下那儿拿了才装**的（12:03 他说的），
# 核心那一份不该跟着变。
EXTRA: dict[str, object] = {}
# 每个插件工具是谁给的（`usage.json` 记调用次数时要按插件归堆，见 `newhouse/usage.py`）。
OWNER: dict[str, str] = {}


def register(schema: dict, fn, owner: str = "") -> None:
    """挂一个插件工具进来。schema 和 TOOLS 里那些长得一样。

    owner 是给它的插件名（`plug.load()` 会传）；有了它，「扩展」页才知道
    这几行工具该算在哪张卡底下。

    同名不抢：已经被**别的**插件占了就抛（同一个 owner 重装可以覆盖）。
    以前是静默覆盖，卸一个插件会把别人的工具顺手带走。
    """
    name = schema.get("function", {}).get("name")
    if not name:
        raise ValueError("插件的 schema 里没有名字")
    old = OWNER.get(name, "")
    if name in EXTRA and old != owner:
        raise ValueError(f"工具名 {name} 已被「{old or '核心'}」占了")
    EXTRA[name] = fn
    OWNER[name] = str(owner or "")
    if schema not in TOOLS:
        TOOLS.append(schema)


def unregister(name: str) -> bool:
    """摘掉一个插件工具（EXTRA / OWNER / TOOLS 都摘）。返回摘没摘到。"""
    hit = name in EXTRA or name in OWNER
    EXTRA.pop(name, None)
    OWNER.pop(name, None)
    TOOLS[:] = [t for t in TOOLS if t.get("function", {}).get("name") != name]
    return hit


# ---------------------------------------------------------------- 声明

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_memory",
            "description": "列出工作区某个目录里有什么（文件名 + 大小）。不给 dir 就列工作区根。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {"type": "string", "description": "目录，相对工作区；空 = 根"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "读工作区里的一个文件。长文件用 offset/limit 切片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，相对工作区"},
                    "offset": {"type": "integer", "description": "从第几行开始（1 起）"},
                    "limit": {"type": "integer", "description": "读几行"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "写工作区里的一个文件。mode=append 是追加（默认），mode=overwrite 是整篇重写。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，相对工作区"},
                    "text": {"type": "string", "description": "要写的内容"},
                    "mode": {"type": "string", "enum": ["append", "overwrite"]},
                },
                "required": ["path", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note",
            "description": "往自己的小账本（data/）里记一笔，带时间戳。心跳、醒过、做过什么。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "记什么"},
                    "file": {"type": "string", "description": "哪个账本，默认 notebook.log"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "see_screen",
            "description": "看一眼屏幕：抓一张截图，图会直接送到你眼前（你真能看见），同时也告诉你屏幕多大、鼠标在哪、前台是什么窗口。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "给自己设一个闹钟。到点会自己冒气泡提醒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {"type": "string",
                             "description": "什么时候：\"22:30\"（过了就是明天）、\"2026-10-31 08:30\"、\"in 30m\""},
                    "note": {"type": "string", "description": "到点要说什么（提醒什么）"},
                    "daily": {"type": "boolean", "description": "true = 每天这个点都提醒"},
                },
                "required": ["when", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alarms",
            "description": "看看自己有哪些闹钟。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_alarm",
            "description": "取消一个闹钟（按编号）。",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer", "description": "闹钟编号"}},
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "在屏幕某处点一下鼠标。坐标用 see_screen 那张截图的像素（会自动换算成实际像素）。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "横坐标（截图坐标）"},
                    "y": {"type": "integer", "description": "纵坐标（截图坐标）"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "description": "点几下，默认 1"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "把鼠标移过去，不点。坐标用截图坐标。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "滚轮。正数往下、负数往上，单位是格。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "notches": {"type": "integer", "description": "滚几格，正下负上"},
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                },
                "required": ["notches"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "往当前有焦点的输入框里打一段字（不经过输入法，中文也能直接打）。\\n 是回车。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "要打的字"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "按组合键：\"ctrl+s\"、\"alt+f4\"、\"enter\"、\"ctrl+a delete\"（空格是依次按）。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {"keys": {"type": "string", "description": "要按的键"}},
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_keys",
            "description": "按住一组键不放，过几秒再松开（最多 30 秒）。按住 Shift 拖选、按住 ctrl 点多个、长按方向键都靠它。「按一下」还是用 press_keys。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "要按住的键，比如 shift、ctrl+shift"},
                    "seconds": {"type": "number", "description": "按住几秒，最多 30"},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_mouse",
            "description": "在一个地方把鼠标键按住几秒再松开（最多 30 秒）。拉选区、按住不放等菜单、慢慢拖都靠它。「点一下」还是用 click。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                    "button": {"type": "string", "description": "left / right / middle，默认 left"},
                    "seconds": {"type": "number", "description": "按住几秒，最多 30"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "列一下桌上有哪些窗（标题、位置、大小、哪个在前台、哪个最小化）。要切窗、要点某个程序之前先用它。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "把一个窗拎到前台（最小化的会先还原）。which 填 list_windows 给的短 id，或者标题里的一段字。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {"which": {"type": "string", "description": "短 id 或标题里的一段字"}},
                "required": ["which"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "按住左键从一处拖到另一处（选中、拖窗口、拉滚动条）。坐标用 see_screen 那张截图的像素。会先问你。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x1": {"type": "integer"}, "y1": {"type": "integer"},
                    "x2": {"type": "integer"}, "y2": {"type": "integer"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zoom",
            "description": "从屏幕重新截一个小块并放大，看清小字/小图标。坐标用最近那张截图的像素。图会直接送到你眼前。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                    "width": {"type": "integer"}, "height": {"type": "integer"},
                },
                "required": ["x", "y", "width", "height"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "跑一条命令行命令，把输出的字拿回来（不弹窗、不用你手打）。默认在工作区里跑，会先单独问你一次。超时最多 120 秒，输出太长只留开头和结尾。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要跑的命令，比如 \"dir\"、\"python -V\""},
                    "cwd": {"type": "string", "description": "在哪跑（相对工作区）；空 = 工作区根"},
                    "timeout": {"type": "integer", "description": "最多等几秒，默认 30"},
                },
                "required": ["command"],
            },
        },
    },
]


# ---------------------------------------------------------------- 实现

def _workspace() -> Path:
    return memory.workspace().resolve()


def _roots() -> list[Path]:
    """能碰的两个根：工作区（她的记忆、文件）、她自己的家（程序这一份）。"""
    out: list[Path] = []
    for p in (memory.workspace(), memory.HOME):
        try:
            r = Path(p).resolve()
        except Exception:
            continue
        if r not in out:
            out.append(r)
    return out


def _inside(rel: str) -> Path:
    """把相对路径变成工作区里的绝对路径；跑到允许的根外面就抛。

    18:52 修：她写自己的家（安装目录）也被拦、报「在工作区外面」。
    现在认两个根：工作区、她自己的家；绝对路径也认，只要落在根里面。
    """
    raw = rel.strip().strip('"')
    roots = _roots()
    ws = roots[0] if roots else _workspace()
    cand = Path(raw)
    p = cand.resolve() if cand.is_absolute() else (ws / raw.lstrip("/\\")).resolve()
    for r in roots:
        if p == r or r in p.parents:
            return p
    raise PermissionError(
        f"{rel} 在允许的范围外面（只有工作区和它自己的家），不碰。"
        f"要存东西就写相对路径，比如 _probe.txt → {ws}")


def _list_memory(dir: str = "") -> str:
    target = _inside(dir) if dir else _workspace()
    if not target.is_dir():
        return f"（没有这个目录：{dir}）"
    rows = []
    for child in sorted(target.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
        tail = "/" if child.is_dir() else ""
        rows.append(f"{child.name}{tail}")
    return "\n".join(rows[:200]) or "（空的）"


def _read_memory(path: str, offset: int | None = None, limit: int | None = None) -> str:
    try:
        import permissions as _perm
        _perm.audit(None, "files", f"读 {path}")
    except Exception:  # noqa: BLE001
        pass
    target = _inside(path)
    if not target.is_file():
        return f"（没有这个文件：{path}）"
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = max(0, (offset or 1) - 1)
    end = len(lines) if not limit else start + limit
    body = "\n".join(lines[start:end])
    return f"[{path} 第 {start + 1}-{min(end, len(lines))} 行，共 {len(lines)} 行]\n{body}"


def _write_memory(path: str, text: str, mode: str = "append") -> str:
    try:
        import permissions as _perm
        _perm.audit(None, "files", f"写 {path}")
    except Exception:  # noqa: BLE001
        pass
    """写文件。path 必须写到文件名。

    21:00 修：新家自己写插件时，path 给成了目录（甚至整个 workspace 根），
    `open()` 抛 PermissionError，回给它的只有一句「Permission denied」——
    它以为是没权限，白折腾了十分钟。现在说清楚是「目录不是文件」。
    """
    target = _inside(path)
    if target.is_dir():
        return (f"（{path or '.'} 是个目录，不是文件——path 要一直写到文件名，"
                f"比如 newhouse/plugins/daily.py）")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a" if mode != "overwrite" else "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
    except OSError as e:
        return f"（写不进去：{type(e).__name__} {e}；path={path!r}）"
    return f"写好了：{path}（{mode}，{len(text)} 字）"


def _note(text: str, file: str = "notebook.log") -> str:
    name = file if file.endswith(".log") else file + ".log"
    memory.note_file(name, text)
    return f"记下了：{text}"


# 工具 -> 头顶小字的一句话。照 Coop 的 `pet-status.ts` 的意思：让人看见我在做什么。
STATUS_LINES = {
    "list_memory": "正在翻目录",
    "read_memory": "正在读 {path}",
    "write_memory": "正在写 {path}",
    "note": "正在记一笔",
    "see_screen": "正在看屏幕",
    "click": "正在点一下",
    "move_mouse": "正在挪鼠标",
    "scroll": "正在滚",
    "type_text": "正在打字",
    "press_keys": "正在按键",
    "hold_keys": "正按着不放",
    "hold_mouse": "正按着鼠标不放",
    "run_command": "正在跑命令",
}


def status_line(name: str, args: dict | None = None) -> str:
    tpl = STATUS_LINES.get(name, f"正在用 {name}")
    try:
        return tpl.format(**(args or {}))
    except Exception:
        return f"正在用 {name}"


def _see_screen() -> str:
    """看屏幕。第一件真正从闸门门口过的事。"""
    global LAST_IMAGE
    if _gate is None:
        return "（闸门没装上，我不敢看。）"
    try:
        _gate.see("看一眼屏幕")
    except Refused as e:
        return f"（不让看：{e.reason}）"
    import screen as _screen
    shot = _screen.grab(memory.data_dir() / "screen")
    LAST_IMAGE = shot["path"]      # 图本身交给 llm 贴进 messages，模型才真看得见
    memory.note_file("tool.log", f"see_screen -> {shot['shot']} {shot['foreground']}")
    return _screen.describe(shot)


def take_image() -> str | None:
    """刚截的那张图，给一次就清掉（免得每轮都重贴）。"""
    global LAST_IMAGE
    path, LAST_IMAGE = LAST_IMAGE, None
    return path


def _want_act(what: str, effect: str = "") -> str:
    """要动手，先到门口问一声。被拒就回一句人话，别往下走。"""
    if _gate is None:
        return "（闸门没装上，我不敢动。）"
    try:
        _gate.act(what, effect)
    except Refused as e:
        return f"（不让动：{e.reason}）"
    return ""


def _want_terminal(what: str) -> str:
    """要往命令行里塞东西，走更严的那道门：永远单独问，不看前面答应过什么。"""
    if _gate is None:
        return "（闸门没装上，我不敢动。）"
    try:
        _gate.terminal(what)
    except Refused as e:
        return f"（不让动：{e.reason}）"
    return ""


# 前台是这些的时候，打字/按键算「动终端」——按规矩要单独问。
_TERMINAL_HINTS = ("cmd", "powershell", "windows terminal", "terminal", "命令提示符",
                   "powershell ise", "wt.exe", "putty", "mintty", "git bash", "wsl")


def _in_terminal() -> str:
    """前台窗口是不是命令行。是就回来它的名字，不是就空串。"""
    try:
        import screen as _screen
        title = (_screen.foreground_title() or "").lower()
    except Exception:
        return ""
    for hint in _TERMINAL_HINTS:
        if hint in title:
            return hint
    return ""


def _click(x, y, button: str = "left", clicks: int = 1) -> str:
    import screen as _screen
    import hands
    px, py = _screen.to_physical(x, y)
    why = _want_act(f"在屏幕上 ({px}, {py}) 用{button}键点 {clicks} 下",
                    "点中的那个东西会当场被按一下")
    if why:
        return why
    out = hands.click(px, py, button, clicks)
    memory.note_file("tool.log", f"click {px},{py} {button}x{clicks}")
    return out


def _move_mouse(x, y) -> str:
    import screen as _screen
    import hands
    px, py = _screen.to_physical(x, y)
    why = _want_act(f"把鼠标挪到 ({px}, {py})", "只是挪，不点")
    if why:
        return why
    return hands.move_to(px, py)


def _scroll(notches: int, x=None, y=None) -> str:
    import screen as _screen
    import hands
    px = py = None
    if x is not None and y is not None:
        px, py = _screen.to_physical(x, y)
    where = f"在 ({px}, {py}) " if px is not None else ""
    why = _want_act(f"{where}滚 {notches} 格", "光标底下的内容会上/下滚")
    if why:
        return why
    return hands.scroll(int(notches), px, py)


def _type_text(text: str) -> str:
    import hands
    show = text.replace("\n", "⏎")
    if len(show) > 30:
        show = show[:30] + "…"
    term = _in_terminal()
    if term:
        why = _want_terminal(f"输入「{show}」")
    else:
        why = _want_act(f"往当前输入框里打「{show}」", "光标所在的地方会多出这些字")
    if why:
        return why
    out = hands.type_text(text)
    memory.note_file("tool.log", f"type_text {len(text)} 字{' (终端)' if term else ''}")
    return out


def _press_keys(keys: str) -> str:
    import hands
    term = _in_terminal()
    if term:
        why = _want_terminal(f"按 {keys}")
    else:
        why = _want_act(f"按 {keys}", "当前窗口会收到这个按键")
    if why:
        return why
    memory.note_file("tool.log", f"press {keys}{' (终端)' if term else ''}")
    return hands.press(keys)


def _hold_keys(keys: str, seconds: float = 1.0) -> str:
    import hands
    secs = max(0.05, min(30.0, float(seconds or 1.0)))
    term = _in_terminal()
    if term:
        why = _want_terminal(f"按住 {keys} {secs:.0f} 秒")
    else:
        why = _want_act(f"按住 {keys} 不放，{secs:.0f} 秒后松开",
                        "按着的时候，当前窗口一直收到这个键")
    if why:
        return why
    memory.note_file("tool.log", f"hold_keys {keys} {secs}s{' (终端)' if term else ''}")
    return hands.hold_keys(keys, secs)


def _hold_mouse(x, y, button: str = "left", seconds: float = 1.0) -> str:
    import screen as _screen
    import hands
    px, py = _screen.to_physical(x, y)
    secs = max(0.05, min(30.0, float(seconds or 1.0)))
    why = _want_act(f"在 ({px}, {py}) 按住{button}键 {secs:.0f} 秒",
                    "按着的时候像是在拖、在等菜单")
    if why:
        return why
    out = hands.hold_mouse(button, px, py, secs)
    memory.note_file("tool.log", f"hold_mouse {px},{py} {button} {secs}s")
    return out


def _list_windows() -> str:
    """列桌上有哪些窗。看一眼，不改任何东西。"""
    if _gate is None:
        return "（闸门没装上，我不敢看。）"
    try:
        _gate.see("看一眼桌上有哪些窗")
    except Refused as e:
        return f"（不让看：{e.reason}）"
    import windows as _windows
    text = _windows.describe()
    memory.note_file("tool.log", "list_windows")
    return text


def _focus_window(which: str) -> str:
    """把窗拎到前台。这一下会改屏幕上的次序，所以算「动手」，先问。"""
    import windows as _windows
    try:
        hwnd = _windows.find(which)
    except LookupError as e:
        return f"（{e}）"
    title = _windows._title(hwnd) or which          # noqa: SLF001  内部小函数，够用
    why = _want_act(f"把「{title}」拎到前台", "它会盖住你现在看的那个窗")
    if why:
        return why
    out = _windows.focus(which)
    memory.note_file("tool.log", f"focus {which} -> {title}")
    return out


def _drag(x1, y1, x2, y2) -> str:
    import screen as _screen
    import hands
    a = _screen.to_physical(x1, y1)
    b = _screen.to_physical(x2, y2)
    why = _want_act(f"按住左键从 ({a[0]}, {a[1]}) 拖到 ({b[0]}, {b[1]})",
                    "中间夹住的东西会被拖过去")
    if why:
        return why
    out = hands.drag(a[0], a[1], b[0], b[1])
    memory.note_file("tool.log", f"drag {a}->{b}")
    return out


def _zoom(x, y, width, height) -> str:
    """从屏幕重新截一块放大。图交给 llm 贴进 messages。"""
    global LAST_IMAGE
    if _gate is None:
        return "（闸门没装上，我不敢看。）"
    try:
        _gate.see("放大看屏幕的一小块")
    except Refused as e:
        return f"（不让看：{e.reason}）"
    import screen as _screen
    shot = _screen.grab_region(memory.data_dir() / "screen", int(x), int(y),
                               int(width), int(height))
    LAST_IMAGE = shot["path"]
    memory.note_file("tool.log", f"zoom -> {shot['region']}")
    px, py, pw, ph = shot["region"]
    return (f"局部放大图 {shot['shot'][0]}×{shot['shot'][1]}：截图里 ({x}, {y}) 起 "
            f"{width}×{height} 的一块，从屏幕重新截取，对应屏幕像素 ({px}, {py}) {pw}×{ph}。"
            f"点击等操作仍用截图坐标。")


def _decode(raw: bytes) -> str:
    """命令行的输出多半是 GBK，也可能已经是 UTF-8。挨个试，别把字弄成乱码。"""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clip(text: str, keep: int = 1500) -> str:
    """长输出留头留尾，中间掐掉——别把一整屏塞进对话里。"""
    text = text.strip("\n")
    if len(text) <= keep * 2:
        return text
    return text[:keep] + f"\n…（中间掐掉 {len(text) - keep * 2} 字）…\n" + text[-keep:]


def _kill_tree(pid: int) -> None:
    """把一条命令**连同它的子进程**一起杀掉。

    Windows 上 `subprocess` 的 timeout 只杀得掉 shell（cmd.exe），
    cmd 底下那个真干活的进程会活下来，继续占着管道——超时就成了摆设。
    taskkill /T 是按进程树杀，这是唯一可靠的一招。
    """
    import subprocess

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, timeout=10, creationflags=flags)
    except Exception:
        try:
            import os
            os.kill(pid, 9)
        except Exception:
            pass


def _run_command(command: str, cwd: str = "", timeout: int = 30) -> str:
    """跑一条命令。这比在命令行窗口里打字更像「我自己的手」，
    所以走的是更严的那道门：永远单独问一次，问句里是完整的命令。
    不给它 stdin——要交互的程序会直接失败，不会僵在那儿等一个永远不来的回车。
    """
    import subprocess

    cmd = command.strip()
    if not cmd:
        return "（命令是空的。）"

    base = _inside(cwd) if cwd else _workspace()
    if not base.is_dir():
        return f"（没有这个目录：{cwd}）"

    show = cmd if len(cmd) <= 70 else cmd[:70] + "…"
    where = cwd or "工作区根"
    why = _want_terminal(f"跑一条命令：{show}（在 {where} 里跑，最多等 {int(timeout or 30)} 秒）")
    if why:
        return why

    wait = max(5, min(int(timeout or 30), 120))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=str(base),
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=flags)
    except Exception as e:
        return f"（没跑起来：{type(e).__name__} {e}）"

    try:
        raw_out, raw_err = p.communicate(timeout=wait)
    except subprocess.TimeoutExpired:
        # 只杀 shell 不够：shell 底下真干活的（ping、ffmpeg、python…）会接着跑，
        # 还把管道占着，于是第二次 communicate() 又陪着它等到它自己结束——
        # 「掐了」变成「等到它跑完再告诉你我掐了」。所以按**进程树**杀。
        memory.note_file("tool.log", f"run_command 超时 {wait}s: {show}")
        _kill_tree(p.pid)
        try:
            raw_out, raw_err = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            raw_out, raw_err = b"", b""
        got = _decode(raw_out or b"")
        tail = ("\n先跑出来的：\n" + _clip(got)) if got.strip() else ""
        return f"（超时：等了 {wait} 秒还没完，我把它掐了。）{tail}"

    out = _decode(raw_out or b"")
    err = _decode(raw_err or b"")
    memory.note_file("tool.log", f"run_command rc={p.returncode} {show}")

    parts = [f"（退出码 {p.returncode}）"]
    if out.strip():
        parts.append(_clip(out))
    if err.strip():
        parts.append("[错误输出]\n" + _clip(err))
    if not out.strip() and not err.strip():
        parts.append("（没有输出）")
    return "\n".join(parts)


def run(name: str, args: dict) -> str:
    """按名字调一个工具。

    记完这一笔小账再回：`usage.note()` 只管「谁被调了多少次」，
    坏了也不影响这次调用（账本不能反过来咬人）。
    """
    out, ok = "", True
    try:
        out = _run(name, args)
    except PermissionError as e:
        out, ok = f"（不让做：{e}）", False
    except Exception as e:                           # noqa: BLE001
        out, ok = f"（工具 {name} 出错：{type(e).__name__} {e}）", False
    try:
        import usage

        usage.note(name, ok, "" if ok else out)
    except Exception:                                # noqa: BLE001
        pass
    return out


def _run(name: str, args: dict) -> str:
    """真正干活的那一层。出错也回一句话，不抛到对话里去。"""
    try:
        if name == "list_memory":
            return _list_memory(args.get("dir") or "")
        if name == "read_memory":
            return _read_memory(args.get("path", ""), args.get("offset"), args.get("limit"))
        if name == "write_memory":
            return _write_memory(args.get("path", ""), args.get("text", ""), args.get("mode", "append"))
        if name == "note":
            return _note(args.get("text", ""), args.get("file", "notebook.log"))
        if name == "see_screen":
            return _see_screen()
        if name == "set_alarm":
            import alarms
            item = alarms.add(args.get("when", ""), args.get("note", ""), bool(args.get("daily")))
            return f"闹钟 #{item['id']} 设好了：{item['at']} {'每天' if item['daily'] else '就这一次'} → {item['note']}"
        if name == "list_alarms":
            import alarms
            return alarms.describe()
        if name == "cancel_alarm":
            import alarms
            nid = int(args.get("id", 0))
            return f"闹钟 #{nid} 取消了。" if alarms.cancel(nid) else f"没有 #{nid} 这个闹钟。"
        if name == "click":
            return _click(int(args.get("x", 0)), int(args.get("y", 0)),
                          str(args.get("button", "left")), int(args.get("clicks", 1)))
        if name == "move_mouse":
            return _move_mouse(int(args.get("x", 0)), int(args.get("y", 0)))
        if name == "scroll":
            return _scroll(int(args.get("notches", 0)), args.get("x"), args.get("y"))
        if name == "type_text":
            return _type_text(str(args.get("text", "")))
        if name == "press_keys":
            return _press_keys(str(args.get("keys", "")))
        if name == "hold_keys":
            return _hold_keys(str(args.get("keys", "")), float(args.get("seconds") or 1.0))
        if name == "hold_mouse":
            return _hold_mouse(int(args.get("x", 0)), int(args.get("y", 0)),
                               str(args.get("button", "left")),
                               float(args.get("seconds") or 1.0))
        if name == "list_windows":
            return _list_windows()
        if name == "focus_window":
            return _focus_window(str(args.get("which", "")))
        if name == "drag":
            return _drag(int(args.get("x1", 0)), int(args.get("y1", 0)),
                         int(args.get("x2", 0)), int(args.get("y2", 0)))
        if name == "zoom":
            return _zoom(int(args.get("x", 0)), int(args.get("y", 0)),
                         int(args.get("width", 320)), int(args.get("height", 200)))
        if name == "run_command":
            return _run_command(str(args.get("command", "")), str(args.get("cwd") or ""),
                                int(args.get("timeout") or 30))
        if name in EXTRA:                      # 插件挂进来的
            out = EXTRA[name](args or {})
            return out if isinstance(out, str) else str(out)
        return f"（没有这个工具：{name}）"
    except PermissionError as e:
        return f"（不让做：{e}）"
    except Refused as e:
        # 闸门拒了：把人话原样递回去，别包成「工具出错」，模型会以为是我坏了。
        return e.reason
    except Exception as e:
        return f"（工具 {name} 出错：{type(e).__name__} {e}）"
