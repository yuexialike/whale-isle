"""手：动鼠标、按键、打字。

只做动作，不管「准不准动」——那个由 gate 决定，工具层去问。
从 Coop 的 `cua/*.ts` 学的是**小心**：一次只做一件、做完就停、坐标全用绝对像素；
代码是我自己用 ctypes 写的，没搬它的（它那边走的是另一套原生插件）。

为什么要 `dpi_aware()`：不调的话 SetCursorPos 用的是逻辑坐标，
150% 缩放时点哪偏哪。跟 screen.py 同一个道理。

打中文用 KEYEVENTF_UNICODE，一个字符一个字符直接塞进去，
不经过输入法——所以不管他那边切的是拼音还是英文，字都一样出来。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

# 64 位窗口上 ULONG_PTR 是 8 字节，写错整个结构体就歪了
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _send(*inputs: INPUT) -> None:
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _mouse(flags: int, data: int = 0) -> None:
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, data, flags, 0, 0)))


def _key(vk: int, up: bool = False) -> None:
    _send(INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)))


def _char(ch: str, up: bool = False) -> None:
    code = ord(ch)
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, code, flags, 0, 0)))


# ---------------------------------------------------------------- 鼠标

def cursor() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def move_to(x: int, y: int) -> str:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    cx, cy = cursor()
    return f"鼠标移到 ({cx}, {cy})"


def click(x: int | None = None, y: int | None = None, button: str = "left",
          clicks: int = 1) -> str:
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
    down, up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))

    for _ in range(max(1, int(clicks))):
        _mouse(down)
        time.sleep(0.03)
        _mouse(up)
        time.sleep(0.06)
    cx, cy = cursor()
    return f"在 ({cx}, {cy}) {button} 键点了 {clicks} 下"


def scroll(notches: int, x: int | None = None, y: int | None = None) -> str:
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
    _mouse(MOUSEEVENTF_WHEEL, int(notches) * 120)
    return f"滚了 {notches} 格"


def drag(x1: int, y1: int, x2: int, y2: int) -> str:
    user32.SetCursorPos(int(x1), int(y1))
    time.sleep(0.08)
    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.08)
    steps = 8
    for i in range(1, steps + 1):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.02)
    _mouse(MOUSEEVENTF_LEFTUP)
    return f"从 ({x1}, {y1}) 拖到 ({x2}, {y2})"


# ---------------------------------------------------------------- 键盘

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "caps": 0x14, "printscreen": 0x2C,
}
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)


def press(combo: str) -> str:
    """按一个组合键。`ctrl+s`、`alt+f4`、`ctrl+a delete`（空格 = 依次按）。"""
    seq = [p for p in (combo or "").split() if p]
    if not seq:
        return "（没说要按什么）"
    for step in seq:
        keys = [k.strip().lower() for k in step.split("+") if k.strip()]
        vks = []
        for k in keys:
            if k not in VK:
                return f"（不认识的键：{k}）"
            vks.append(VK[k])
        for vk in vks:                       # 按下去：先按修饰键，再按主键
            _key(vk, up=False)
            time.sleep(0.02)
        for vk in reversed(vks):             # 松开：反着来
            _key(vk, up=True)
            time.sleep(0.02)
        time.sleep(0.05)
    return f"按了 {combo}"


def type_text(text: str, per_char: float = 0.01) -> str:
    """一段字直接打进去（走 Unicode，不经过输入法）。\\n = 回车。"""
    for ch in text or "":
        if ch == "\n":
            _key(0x0D, up=False)
            time.sleep(0.02)
            _key(0x0D, up=True)
        else:
            _char(ch, up=False)
            _char(ch, up=True)
        time.sleep(per_char)
    return f"打了 {len(text or '')} 个字"


# ---------------------------------------------------------------- 按住不放
# 11-06 15:55 学 Coop 0.2.18 的那条「电脑操作能按住」：
#   以前只有「按一下」，拖选区、按住 Shift 多选、长按右键菜单这些做不出来。
# 规矩：最多 30 秒；不管怎么结束，最后一定松开——一轮结束时 main 会调 release_all()。

_held_vks: list[int] = []
_held_buttons: list[str] = []

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _vks_of(combo: str) -> list[int]:
    """`ctrl+shift` → [0x11, 0x10]。认不出就当成空。"""
    vks = []
    for k in (combo or "").replace(" ", "").split("+"):
        k = k.strip().lower()
        if k and k in VK:
            vks.append(VK[k])
    return vks


def key_down(combo: str) -> str:
    vks = _vks_of(combo)
    if not vks:
        return f"（不认识的键：{combo}）"
    for vk in vks:
        _key(vk, up=False)
        _held_vks.append(vk)
        time.sleep(0.02)
    return f"{combo} 按住了"


def key_up(combo: str | None = None) -> str:
    if combo is None:
        vks = list(_held_vks)
    else:
        want = set(_vks_of(combo))
        vks = [v for v in _held_vks if v in want]
    for vk in reversed(vks):                 # 松开的顺序和按下时反着来
        _key(vk, up=True)
        try:
            _held_vks.remove(vk)
        except ValueError:
            pass
        time.sleep(0.02)
    return f"松开了 {len(vks)} 个键"


def mouse_down(button: str = "left", x: int | None = None, y: int | None = None) -> str:
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
    down = BUTTONS.get(button, BUTTONS["left"])[0]
    _mouse(down)
    _held_buttons.append(button)
    return f"{button} 键按下去了"


def mouse_up(button: str | None = None) -> str:
    target = button or (_held_buttons[-1] if _held_buttons else "left")
    up = BUTTONS.get(target, BUTTONS["left"])[1]
    _mouse(up)
    try:
        _held_buttons.remove(target)
    except ValueError:
        pass
    return f"{target} 键松开了"


def hold_keys(combo: str, seconds: float = 1.0) -> str:
    """按住一组键 seconds 秒（最多 30），到点松开。"""
    seconds = max(0.05, min(30.0, float(seconds)))
    out = key_down(combo)
    if out.startswith("（"):
        return out
    try:                                    # 真出岔子也得松开，不能让键盘卡在按下状态
        time.sleep(seconds)
    finally:
        key_up(combo)
    return f"{out}，{seconds:.1f} 秒后松开"


def hold_mouse(button: str = "left", x: int | None = None, y: int | None = None,
               seconds: float = 1.0) -> str:
    """在一个地方按住鼠标键 seconds 秒（最多 30），到点松开。"""
    seconds = max(0.05, min(30.0, float(seconds)))
    out = mouse_down(button, x, y)
    try:
        time.sleep(seconds)
    finally:
        mouse_up(button)
    return f"{out}，{seconds:.1f} 秒后松开"


def release_all() -> str:
    """把还按着的东西全松开。一轮结束、出错、退出都调它——别让键盘卡在按下状态。"""
    n = 0
    while _held_vks:
        _key(_held_vks.pop(), up=True)
        n += 1
    while _held_buttons:
        b = _held_buttons.pop()
        _mouse(BUTTONS.get(b, BUTTONS["left"])[1])
        n += 1
    return f"松开了 {n} 个还按着的东西" if n else "没有按着的东西"


def self_check() -> str:
    """不动鼠标：只看结构体和系统调用在不在。开机自检用。"""
    x, y = cursor()
    ok = ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
    return f"手: {'ok' if ok else '结构体大小不对'} · INPUT={ctypes.sizeof(INPUT)} · 鼠标在 ({x}, {y})"
